#UO Classic Client formats
#thanks to http://uo.stratics.com/heptazane/fileformats.shtml

from inc_noesis import *
import time
import os
import re

UO_NEW_MULTI_VER = True #set to false to load legacy multi files
UO_NEW_TILEDATA_VER = True #set to false to load legacy (before switching flags to 64-bit) tiledata

UO_TILE_MAX_ALTITUDE = None #set to integer value to clip blocks above this altitude
UO_SKIP_NODRAW = True #skip drawing nodraw tiles

UO_NAME_EXTRACTED_BY_INDEX = False #if true, name extracted mul files by their index instead of the extracted order

UO_DEBUG_BLOCK_ALTITUDES = False #renders altitudes over blocks

UO_MAP_HEIGHTS = (512, 512, 200, 256, 181, 512)
UO_TERRAIN_BLOCK_WIDTH = 44
UO_TERRAIN_BLOCK_HEIGHT = 44

UO_CELLREAD_FLAG_NORMALS = (1 << 0)

#adjusts contribution for terrain normals
UO_TERRAIN_NORMAL_XYSCALE = 1.0
UO_TERRAIN_NORMAL_ZSCALE = 1.0
#terrain lighting parameters
UO_TERRAIN_LIGHT_DIR = (0.0, 0.0, 1.0)
UO_TERRAIN_LIGHT_AMBIENT = 0.4
UO_TERRAIN_LIGHT_DIRECT = 0.4
#terrain read flags
UO_TERRAIN_READ_FLAGS = UO_CELLREAD_FLAG_NORMALS

def registerNoesisTypes():
	handle = noesis.register("Ultima Online UOP Archive", ".uop")
	noesis.setHandlerExtractArc(handle, extractUOP)
	
	handle = noesis.register("Ultima Online MUL Archive", ".mul")
	noesis.setHandlerExtractArc(handle, extractMUL)
	
	handle = noesis.register("Ultima Online Anim", ".uo_anim")
	noesis.setHandlerTypeCheck(handle, uoAnimCheckType)
	noesis.setHandlerLoadRGBA(handle, uoAnimLoadRGBA)

	handle = noesis.register("Ultima Online Gump", ".uo_gump")
	noesis.setHandlerTypeCheck(handle, uoGumpCheckType)
	noesis.setHandlerLoadRGBA(handle, uoGumpLoadRGBA)

	handle = noesis.register("Ultima Online Tex", ".uo_tex")
	noesis.setHandlerTypeCheck(handle, uoTexCheckType)
	noesis.setHandlerLoadRGBA(handle, uoTexLoadRGBA)

	handle = noesis.register("Ultima Online Art Tile", ".uo_art_tile")
	noesis.setHandlerTypeCheck(handle, uoArtTileCheckType)
	noesis.setHandlerLoadRGBA(handle, uoArtTileLoadRGBA)

	handle = noesis.register("Ultima Online Multi-Tile", ".uo_multi_tile")
	noesis.setHandlerTypeCheck(handle, uoMultiTileCheckType)
	noesis.setHandlerLoadRGBA(handle, uoMultiTileLoadRGBA)

	handle = noesis.register("Ultima Online Map", ".uo_map")
	noesis.setHandlerTypeCheck(handle, uoMapCheckType)
	noesis.setHandlerLoadRGBA(handle, uoMapLoadRGBA)
	noesis.addOption(handle, "-uomapterrain", "renders map in region <arg>, formatting is x;y;w;h.", noesis.OPTFLAG_WANTARG)
	
	return 1

class UOPEntry:
	def __init__(self, explicitId, nameHash, dataOfs, compType, readSize, decompSize):
		self.explicitId = explicitId
		self.nameHash = nameHash
		self.dataOfs = dataOfs
		self.compType = compType
		self.readSize = readSize
		self.decompSize = decompSize
		
	def Compare(a, b):
		val = a.explicitId - b.explicitId
		if val == 0:
			val = a.dataOfs - b.dataOfs
		return val
	
def parseUOPEntries(f, baseName, blockOfs, totalFileCount):
	uopEntries = []
	#this could work for maps, but we don't need it since we're able to derive the index from the hash.
	#if hashes are failing for maps, enabling it will probably fix the problem. otherwise the map slices
	#will end up out of order.
	useSortKey = False #baseName.startswith("map")

	while blockOfs != 0 and len(uopEntries) < totalFileCount:
		f.seek(blockOfs, os.SEEK_SET)
		fileCount, blockOfs = noeUnpack("<IQ", f.read(12))
		blockFileData = f.read(34 * fileCount)
		for fileIndex in range(0, fileCount):
			entryData = blockFileData[34 * fileIndex : 34 * fileIndex + 34]
			hdrOfs, hdrSize, compSize, decompSize, nameHash, dataHash, compType = noeUnpack("<QIIIQIH", entryData)
			f.seek(hdrOfs, os.SEEK_SET)
			dataType, dataOfs = noeUnpack("<HH", f.read(4))
			f.seek(dataOfs, os.SEEK_CUR)
			readSize = compSize if compSize > 0 else decompSize

			if useSortKey:
				sortKey = noeUnpack("<I", f.read(4))[0] // 4096 if useSortKey else 0
				f.seek(-4, os.SEEK_CUR)

			if readSize > 0:
				explicitId = sortKey if useSortKey else rapi.callExtensionMethod("uo_id_for_hash", nameHash)					
				uopEntry = UOPEntry(explicitId, nameHash, f.tell(), compType, readSize, decompSize)
				uopEntries.append(uopEntry)
				if len(uopEntries) >= totalFileCount:
					break
	return uopEntries

def extractUOP(fileName, fileLen, justChecking):
	if fileLen < 28:
		return 0

	with open(fileName, "rb") as f:
		id, ver, unk, blockOfs, maxFilesPerBlock, totalFileCount = noeUnpack("<IIIQII", f.read(28))
		if id != 0x50594D: #"MYP\0"
			return 0
		if ver < 4 or ver > 5:
			return 0
		if totalFileCount == 0:
			return 0
			
		if justChecking:
			return 1
			
		baseName = rapi.getExtensionlessName(rapi.getLocalFileName(fileName)).lower()
		
		#the typical form used is:
		#hash = rapi.callExtensionMethod("uo_hash_war", "build/uop/########.*", 0xDEADBEEF)
		#however, many uop's use explicit names and/or different extensions. for our purposes we only care about trying to preserve id's.
		#this will at least cover everything in artLegacyMUL (at the moment), so that multi's can map correctly.
		print("Priming hash...")
		rapi.callExtensionMethod("uo_reset_hash")
		rapi.callExtensionMethod("uo_prime_hash", "build/" + baseName + "/", ".bin", 0, 131072, 8, 0xDEADBEEF)
		rapi.callExtensionMethod("uo_prime_hash", "build/" + baseName + "/", ".dds", 0, 131072, 8, 0xDEADBEEF)
		rapi.callExtensionMethod("uo_prime_hash", "build/" + baseName + "/", ".tga", 0, 131072, 8, 0xDEADBEEF)
		rapi.callExtensionMethod("uo_prime_hash", "build/" + baseName + "/", ".dat", 0, 131072, 8, 0xDEADBEEF)
		#explicit hashes can be associated with id's like this:
		#rapi.callExtensionMethod("uo_hash_for_id", "build/whatever/balls.bin", 0xDEADBEEF, 1337)
		
		uopEntries = parseUOPEntries(f, baseName, blockOfs, totalFileCount) 

		if len(uopEntries) == 0:
			print("No exportable files found in UOP.")
			return 1

		uopEntries = sorted(uopEntries, key=noeCmpToKey(UOPEntry.Compare))
		
		#create index and mul data bytearrays, then just export them as archive files (convenience)
		idxData = bytearray()
		idxDataNonExplicit = bytearray()
		mulData = bytearray()
		for uopEntry in uopEntries:
			f.seek(uopEntry.dataOfs, os.SEEK_SET)
			srcData = f.read(uopEntry.readSize)
			if uopEntry.compType == 1:
				dstData = rapi.decompInflate(srcData, uopEntry.decompSize)
			else:
				dstData = srcData					
			print("Writing data at", uopEntry.dataOfs, "-", "id:", uopEntry.explicitId, "size:", len(dstData), "hash:", uopEntry.nameHash)
			packedIdx = noePack("III", len(mulData), len(dstData), 0)
			if uopEntry.explicitId != 0xFFFFFFFF:
				desiredOfs = uopEntry.explicitId * 12
				if len(idxData) <= desiredOfs:
					#pad out up to the desired entry
					padCount = ((desiredOfs - len(idxData)) + 1) // 12
					idxData += noePack("III", 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF) * padCount
				idxData[desiredOfs : desiredOfs + 12] = packedIdx
			else:
				#make sure anything with a non-explicit id gets tacked onto the end
				idxDataNonExplicit += packedIdx
			mulData += dstData

		print("Writing " + baseName + ".idx and .mul...")
		if baseName.startswith("map"):
			print("Exporting MUL data as uo_map due to filename.")
			uoMapHeader = noePack("II", len(idxData) + len(idxDataNonExplicit), len(mulData))
			rapi.exportArchiveFile(baseName + ".uo_map", uoMapHeader + idxData + idxDataNonExplicit + mulData)
		else:
			rapi.exportArchiveFile(baseName + ".idx", idxData + idxDataNonExplicit)
			rapi.exportArchiveFile(baseName + ".mul", mulData)
		
		return 1

	return 0

def findIDXForMUL(baseName):
	testName = baseName + ".idx"
	if os.path.exists(testName):
		return testName
	testName = baseName + "idx.mul"
	if os.path.exists(testName):
		return testName
		
	path, name = os.path.split(baseName)
	if name.startswith("statics"):
		testName = path + "/" + name.replace("statics", "staidx") + ".mul"
		if os.path.exists(testName):
			return testName
	elif name.startswith("texmaps"):
		testName = path + "/" + name.replace("texmaps", "texidx") + ".mul"
		if os.path.exists(testName):
			return testName
	elif name == "gumpart":
		testName = path + "/" + "gumpidx.mul"
		if os.path.exists(testName):
			return testName
	
	return None
	
def mulPassthroughHandler(rawData, rawIndex, mulName, offsetInMul, sizeInMul, resvValue):
	#applies to any format that doesn't require export processing
	return rawData

def mulGumpHandler(rawData, rawIndex, mulName, offsetInMul, sizeInMul, resvValue):
	#pack the dimensions from the index into the output binary
	return noePack("HH", (resvValue & 0xFFFF), ((resvValue >> 16) & 0xFFFF)) + rawData

def mulSoundHandler(rawData, rawIndex, mulName, offsetInMul, sizeInMul, resvValue):
	#sample/bit rate of all sounds is fixed, so just plop it out with a RIFF WAVE header
	waveHeaderData = rapi.createPCMWaveHeader(len(rawData), 16, 22050, 1)
	return waveHeaderData + rawData
	
def extractMUL(fileName, fileLen, justChecking):
	baseName = rapi.getExtensionlessName(fileName).lower()
	idxName = findIDXForMUL(baseName)
	localName = rapi.getLocalFileName(baseName)
	isMap = False
	if not idxName:
		if localName.startswith("map") and (fileLen % 196) == 0:
			mapIndex, mapNumberName = uoGetMapIndexFromFileName(localName)
			mapHeight = UO_MAP_HEIGHTS[mapIndex]
			mapWidth = fileLen // 196 // mapHeight
			if mapWidth >= 8 and mapWidth <= 4096:
				isMap = True
				
		if not isMap:
			return 0
		
	if justChecking:
		return 1
		
	if isMap:
		with open(fileName, "rb") as fMul:
			mulData = fMul.read()
			exName = localName + ".uo_map"
			print("Writing", exName)
			rapi.exportArchiveFile(exName, noePack("<II", 0, len(mulData)) + mulData)
		return 1
		
	supportedPrefixHandlers = (
		("__raw__", ".uo_raw", mulPassthroughHandler), #must remain as first entry
		("animationframe", ".uo_animframe", mulPassthroughHandler),
		("anim", ".uo_anim", mulPassthroughHandler),
		("gump", ".uo_gump", mulGumpHandler),
		("tex", ".uo_tex", mulPassthroughHandler),
		("art", ".uo_art_tile", mulPassthroughHandler),
		("multi", ".uo_multi_tile", mulPassthroughHandler),
		("sound", ".wav", mulSoundHandler)
	)
	useHandler = None
	for handler in supportedPrefixHandlers:
		handlerPrefix = handler[0]
		if localName.startswith(handlerPrefix):
			useHandler = handler
			break
		
	if not useHandler:
		print("No resource handlers found, extracting as unknown/raw.")
		useHandler = supportedPrefixHandlers[0]
	else:
		print("Using MUL handler:", useHandler[0])

	useHandlerPrefix, useHandlerExt, useHandlerFn = useHandler

	exFileCount = 0
	rawIndex = 0
	with open(fileName, "rb") as fMul, open(idxName, "rb") as fIdx:
		while True:
			idxData = fIdx.read(12)
			if not idxData:
				break
			ofs, size, resv = noeUnpack("<III", idxData)
			if ofs != 0xFFFFFFFF and size > 0:
				fMul.seek(ofs, os.SEEK_SET)
				mulData = useHandlerFn(fMul.read(size), rawIndex, localName, ofs, size, resv)
				if mulData is not None:
					nameIndex = rawIndex if UO_NAME_EXTRACTED_BY_INDEX else exFileCount
					exName = localName + "%06i"%nameIndex + useHandlerExt
					exFileCount += 1
					print("Writing", exName)
					rapi.exportArchiveFile(exName, mulData)
			rawIndex += 1

	return 1


def uoAnimCheckType(data):
	if len(data) < 516:
		return 0
	bs = NoeBitStream(data)
	bs.seek(512, NOESEEK_ABS)
	frameCount = bs.readInt()
	if frameCount <= 0 or (516 + frameCount * 4) >= len(data):
		return 0
	for frameIndex in range(0, frameCount):
		ofs = bs.readInt()
		if ofs < 0 or ofs >= len(data):
			return 0
	return 1

def uoAnimLoadRGBA(data, texList):
	bs = NoeBitStream(data)
	palData = bs.readBytes(512)
	palRgba = rapi.imageDecodeRaw(palData, 256, 1, "b5g5r5p1")
	frameCount = bs.readInt()
	frameOffsets = []
	for frameIndex in range(0, frameCount):
		frameOffsets.append(bs.readInt())

	#loop through to get the canvas dimensions first
	maxXOffset = 0
	maxYOffset = 0
	canvasWidth = 0
	canvasHeight = 0
	for frameOffset in frameOffsets:
		bs.seek(512 + frameOffset, NOESEEK_ABS)
		maxXOffset = max(maxXOffset, bs.readShort())
		centerY = bs.readShort()
		maxYOffset = max(maxYOffset, -centerY)
		canvasWidth = max(canvasWidth, bs.readShort())
		height = bs.readShort()
		canvasHeight = max(canvasHeight, height + centerY)
	canvasHeight += maxYOffset
	
	baseTexName = rapi.getExtensionlessName(rapi.getLocalFileName(rapi.getLastCheckedName()))
	for frameOffset in frameOffsets:
		bs.seek(512 + frameOffset, NOESEEK_ABS)
		centerX = bs.readShort()
		centerY = bs.readShort()
		width = bs.readShort()
		height = bs.readShort()
		
		encodedDataOfs = bs.getOffset()
		encodedData = bs.getBuffer()[encodedDataOfs:]
		#decode the pixel data
		decodedData = rapi.callExtensionMethod("uo_anim_decode", encodedData, palRgba, centerX, centerY, width, height, maxXOffset, maxYOffset, canvasWidth, canvasHeight)
		texName = baseTexName + "_frame" + repr(len(texList))
		tex = NoeTexture(texName, canvasWidth, canvasHeight, decodedData, noesis.NOESISTEX_RGBA32)
		texList.append(tex)
	
	return 1

def uoGumpCheckType(data):
	#unique extension will have to be enough for now
	return 1
	
def uoGumpLoadRGBA(data, texList):
	bs = NoeBitStream(data)
	height = bs.readUShort()
	width = bs.readUShort()
	#we read the dimensions as they were embedded from the idx on extraction
	if height == 0 or width == 0:
		#if the resv value was 0 it probably came from a uop, which means it's the new format with embedded width/height
		width = bs.readUInt()
		height = bs.readUInt()
		if height == 0 or width == 0:
			print("Error: Gump has 0 dimensions.") #seems valid, there are some 8-byte stub files
			return 0

	dataOfs = bs.getOffset()
	#decode the pixel data
	decodedData = rapi.callExtensionMethod("uo_gump_decode", bs.getBuffer()[dataOfs:], width, height)
	decodedData = rapi.imageDecodeRaw(decodedData, width, height, "b5g5r5a1")
	tex = NoeTexture("uo_gump_tex", width, height, decodedData, noesis.NOESISTEX_RGBA32)
	texList.append(tex)
	return 1

def uoTexCheckType(data):
	if len(data) != 0x2000 and len(data) != 0x8000:
		return 0
	return 1

def uoTexLoadRGBADirect(data):
	width = 64 if len(data) == 0x2000 else 128
	height = width
	
	rgbaData = rapi.imageDecodeRaw(data, width, height, "b5g5r5p1")
	return NoeTexture("uo_tex_tex", width, height, rgbaData, noesis.NOESISTEX_RGBA32)
	
def uoTexLoadRGBA(data, texList):
	tex = uoTexLoadRGBADirect(data)
	if tex:
		texList.append(tex)
		return 1
	return 0

def uoArtTileCheckType(data):
	#unique extension will have to be enough for now
	return 1
	
def uoArtTileLoadRGBADirect(data):
	bs = NoeBitStream(data)

	if len(data) != 2048: #hack
		#rle
		rawFlag = bs.readUInt()
		width = bs.readUShort()
		height = bs.readUShort()
		decodedData = rapi.callExtensionMethod("uo_arttile_decode", bs.getBuffer()[bs.getOffset():], width, height)
		decodedData = rapi.imageDecodeRaw(decodedData, width, height, "b5g5r5a1")
		tex = NoeTexture("uo_art_rle_tex", width, height, decodedData, noesis.NOESISTEX_RGBA32)
		return tex
	else:
		#raw
		width = 44
		height = 44
		halfWidth = width // 2
		
		startOfs = 1
		startIncr = 1
		imageData = [0] * width * height
		
		y = 0
		while startOfs != 0:
			x = halfWidth - startOfs
			for i in range(0, startOfs * 2): #set the alpha bit on every pixel we write to
				imageData[y * width + x + i] = bs.readUShort() | (1 << 15)

			#possible todo - could optimize, structured this way for easy experimentation (doesn't really matter if these are always 44x44)
			y += 1
			startOfs += startIncr
			if startOfs > halfWidth: #flip
				startOfs = halfWidth
				startIncr = -startIncr

		rgbaData = rapi.imageDecodeRaw(noePack("H" * width * height, *imageData), width, height, "b5g5r5a1")
		tex = NoeTexture("uo_art_raw_tex", width, height, rgbaData, noesis.NOESISTEX_RGBA32)
		return tex
	
	return None
	
def uoArtTileLoadRGBA(data, texList):
	tex = uoArtTileLoadRGBADirect(data)
	if tex:
		texList.append(tex)
		return 1
	return 0

def uoMultiTileCheckType(data):
	#unique extension will have to be enough for now
	return 1
	
def findMulRelativeToFile(fileName, mulName):
	localPath = rapi.getDirForFilePath(fileName)
	for attemptCount in range(1, 4):
		testPath = localPath + "../" * attemptCount
		if os.path.exists(testPath + mulName):
			return testPath
	return None
	
UO_OBJFL_BACKGROUND		= (1 << 0)
UO_OBJFL_WEAPON			= (1 << 1)
UO_OBJFL_TRANSPARENT	= (1 << 2)
UO_OBJFL_TRANSLUCENT	= (1 << 3)
UO_OBJFL_WALL			= (1 << 4)
UO_OBJFL_DAMAGING		= (1 << 5)
UO_OBJFL_IMPASSABLE		= (1 << 6)
UO_OBJFL_WET			= (1 << 7)
UO_OBJFL_UNKNOWN1		= (1 << 8)
UO_OBJFL_SURFACE		= (1 << 9)
UO_OBJFL_BRIDGE			= (1 << 10)
UO_OBJFL_GENERIC		= (1 << 11)
UO_OBJFL_WINDOW			= (1 << 12)
UO_OBJFL_NOSHOOT		= (1 << 13)
UO_OBJFL_ARTICLEA		= (1 << 14)
UO_OBJFL_ARTICLEAN		= (1 << 15)
UO_OBJFL_INTERNAL		= (1 << 16)
UO_OBJFL_FOLIAGE		= (1 << 17)
UO_OBJFL_PARTIALHUE		= (1 << 18)
UO_OBJFL_UNKNOWN2		= (1 << 19)
UO_OBJFL_MAP			= (1 << 20)
UO_OBJFL_CONTAINER		= (1 << 21)
UO_OBJFL_WEARABLE		= (1 << 22)
UO_OBJFL_LIGHTSOURCE	= (1 << 23)
UO_OBJFL_ANIMATION		= (1 << 24)
UO_OBJFL_NODIAGONAL		= (1 << 25)
UO_OBJFL_UNKNOWN3		= (1 << 26)
UO_OBJFL_ARMOR			= (1 << 27)
UO_OBJFL_ROOF			= (1 << 28)
UO_OBJFL_DOOR			= (1 << 29)
UO_OBJFL_STAIRBACK		= (1 << 30)
UO_OBJFL_STAIRRIGHT		= (1 << 31)

UO_DRAWTYPE_LAND		= 0
UO_DRAWTYPE_STATIC		= 1

class UOLandItem:
	def __init__(self, flags, texId, itemName):
		self.flags = flags
		self.texId = texId
		self.itemName = itemName

class UOStaticItem:
	def __init__(self, flags, height, quality, quantity, animId, itemName):
		self.flags = flags
		self.height = height
		self.quality = quality
		self.quantity = quantity
		self.animId = animId
		self.itemName = itemName

class UODrawBlock:
	def __init__(self, sort1, blockX, blockY, blockAltitude, blockFlags, itemId, tileHeight, tileFlags, tex, type, sort2, isTextureMapped):	
		self.sort1 = sort1
		self.blockX = blockX
		self.blockY = blockY
		self.blockAltitude = blockAltitude
		self.blockFlags = blockFlags
		self.itemId = itemId
		self.tileHeight = tileHeight
		self.tileFlags = tileFlags
		self.tex = tex
		self.type = type
		self.sort2 = sort2
		self.isTextureMapped = isTextureMapped
		self.terrainAltitude = None
		self.terrainNormals = None
		self.wasRendered = False
		self.setTerrainGfx(None, 0, 0)
		self.setNeighborData(None)
		self.computeDrawCoord()
		
	def setTerrainGfx(self, terrainGfx, terrainGfxWidth, terrainGfxHeight):
		self.terrainGfx = terrainGfx
		self.terrainGfxWidth = terrainGfxWidth
		self.terrainGfxHeight = terrainGfxHeight
		
	def setNeighborData(self, neighborData):
		self.neighborData = neighborData
		
	def computeDrawCoord(self):
		texW = UO_TERRAIN_BLOCK_WIDTH if self.isTextureMapped else self.tex.width
		texH = UO_TERRAIN_BLOCK_HEIGHT if self.isTextureMapped else self.tex.height
		self.drawX = (self.blockX - self.blockY) * 22 - (texW >> 1)
		self.drawY = (self.blockX + self.blockY) * 22 - texH
		if not self.isTextureMapped:
			self.drawY -= self.blockAltitude * 4
		
	def getSortAltitude(self):
		if self.terrainAltitude is not None:
			return self.terrainAltitude
		return self.blockAltitude
		
	def getTexWidth(self):
		return self.terrainGfxWidth if self.terrainGfx else self.tex.width
		
	def getTexHeight(self):
		return self.terrainGfxHeight if self.terrainGfx else self.tex.height
		
	def __repr__(self):
		return "(x:" + repr(self.drawX) + " y:" + repr(self.drawY) + " sort1:" + repr(self.sort1) + " z:" + repr(self.getSortAltitude()) + " th:" + repr(self.tileHeight) + " fl:" + repr(self.blockFlags) + ")"
		
	def Compare(a, b):
		val = (a.blockX + a.blockY) - (b.blockX + b.blockY)
		if val == 0:
			val = a.type - b.type
			if val == 0:
				val = (a.getSortAltitude() + a.sort1) - (b.getSortAltitude() + b.sort1)
				if val == 0:
					val = a.sort1 - b.sort1
					if val == 0:
						val = a.sort2 - b.sort2
						#could be used as a fallback to handle missing tile data
						#if val == 0:
						#	val = a.tex.height - b.tex.height
		return val
		
def uoIsStaticNoDraw(staticId):
	return staticId == 1 #also 8612, but may vary at different client versions
	
def uoIsLandNoDraw(landId):
	return landId == 2 #also some ohter values, may vary with client version as above, but not sure

def uoLoadTileData(basePath):
	landData = []
	staticData = []
	relPath = findMulRelativeToFile(basePath, "tiledata.mul")
	mulSize = os.path.getsize(relPath + "tiledata.mul")
	if relPath and mulSize > 0: #>= 3188736:
		flagSize = 8 if UO_NEW_TILEDATA_VER else 4
		flagType = "Q" if UO_NEW_TILEDATA_VER else "I"
		with open(relPath + "tiledata.mul", "rb") as fTileData:
			landDataSize = flagSize + 2
			staticDataSize = flagSize + 13
			
			landDataCount = 0x4000 #consistent across all known client versions
			landTotalSize = landDataCount * (landDataSize + 20) + (landDataCount // 32) * 4

			staticGroupSize = 4 + 32 * (staticDataSize + 20)
			remainingItemSize = mulSize - landTotalSize
			if (remainingItemSize % staticGroupSize) == 0:
				staticDataCount = (remainingItemSize // staticGroupSize) * 32 #0x10000
				#fTileData.seek(landTotalSize, os.SEEK_CUR)
				for landIndex in range(0, landDataCount):
					if (landIndex & 31) == 0:
						fTileData.seek(4, os.SEEK_CUR)

					flags, texId = noeUnpack("<" + flagType + "h", fTileData.read(landDataSize));
					tileName = fTileData.read(20)
					landItem = UOLandItem(flags, texId, tileName)
					landData.append(landItem)
					
				for itemIndex in range(0, staticDataCount):
					if (itemIndex & 31) == 0:
						fTileData.seek(4, os.SEEK_CUR)
					flags, weight, quality, unk1, unk2, unk3, quantity, animId, unk4, unk5, val, height = noeUnpack("<" + flagType + "BBBBBBHHBBB", fTileData.read(staticDataSize))
					itemName = fTileData.read(20)
					staticItem = UOStaticItem(flags, height, quality, quantity, animId, itemName)
					staticData.append(staticItem)
			else:
				print("Warning: Remaining tiledata size not aligned to static group size:", remainingItemSize, staticGroupSize)
	return landData, staticData
	
def uoLoadArtTile(blockNum, texDict, fIdx, fMul, asTex = False):
	tex = None
	if blockNum >= 0:
		tex = texDict.get(blockNum)
		if not tex:
			fIdx.seek(12 * blockNum, os.SEEK_SET)
			tileOfs, tileSize = noeUnpack("<II", fIdx.read(8))
			if tileOfs != 0xFFFFFFFF:
				fMul.seek(tileOfs, os.SEEK_SET)
				tileData = fMul.read(tileSize)
				tex = uoTexLoadRGBADirect(tileData) if asTex else uoArtTileLoadRGBADirect(tileData)
				texDict[blockNum] = tex
	return tex

def uoDrawAllBlocks(drawBlocks):
	canvasWidth = 0
	canvasHeight = 0
	minX = 0
	minY = 0
	
	for drawBlock in drawBlocks:
		minX = min(minX, drawBlock.drawX)
		minY = min(minY, drawBlock.drawY)
		canvasWidth = max(canvasWidth, drawBlock.drawX + drawBlock.getTexWidth())
		canvasHeight = max(canvasHeight, drawBlock.drawY + drawBlock.getTexHeight())

	drawBlocks = sorted(drawBlocks, key=noeCmpToKey(UODrawBlock.Compare))
	ofsX = 0
	ofsY = 0
	if minX < 0:
		ofsX = -minX
		canvasWidth += ofsX
	if minY < 0:
		ofsY = -minY
		canvasHeight += ofsY
		
	#draw the blocks into the canvas
	imageData = noePack("BBBB", 0, 0, 0, 0) * canvasWidth * canvasHeight
	for drawBlock in drawBlocks:
		if UO_TILE_MAX_ALTITUDE is not None and drawBlock.getSortAltitude() > UO_TILE_MAX_ALTITUDE:
			continue
		if UO_SKIP_NODRAW:
			if drawBlock.type == UO_DRAWTYPE_STATIC and uoIsStaticNoDraw(drawBlock.itemId):
				continue
			if drawBlock.type == UO_DRAWTYPE_LAND and uoIsLandNoDraw(drawBlock.itemId):
				continue
		if drawBlock.terrainGfx: #pre-rendered terrain data
			rapi.imageBlit32(imageData, canvasWidth, canvasHeight, ofsX + drawBlock.drawX, ofsY + drawBlock.drawY, drawBlock.terrainGfx, drawBlock.terrainGfxWidth, drawBlock.terrainGfxHeight, 0, 0, 0, 0, noesis.BLITFLAG_ALPHABLEND)
		else:
			tex = drawBlock.tex
			rapi.imageBlit32(imageData, canvasWidth, canvasHeight, ofsX + drawBlock.drawX, ofsY + drawBlock.drawY, tex.pixelData, tex.width, tex.height, 0, 0, 0, 0, noesis.BLITFLAG_ALPHABLEND)
		drawBlock.wasRendered = True
			
	if UO_DEBUG_BLOCK_ALTITUDES:
		for drawBlock in drawBlocks:
			if drawBlock.wasRendered:
				rapi.callExtensionMethod("drawtext_8x8_rgba", imageData, canvasWidth, canvasHeight, ofsX + drawBlock.drawX, ofsY + drawBlock.drawY, 0, (127, 255, 0), str(drawBlock.blockAltitude))
			
	return imageData, canvasWidth, canvasHeight
	
def uoMultiTileLoadRGBA(data, texList):
	loadStartTime = time.time()

	relPath = findMulRelativeToFile(rapi.getLastCheckedName(), "artidx.mul")
	if not relPath:
		print("Error: Could not find artidx.mul on any relative path.")
		return 0

	bs = NoeBitStream(data)
	
	loadTileStart = time.time()
	landData, staticData = uoLoadTileData(rapi.getLastCheckedName())
	loadTileTime = time.time() - loadTileStart
	
	loadArtStart = time.time()	
	drawBlocks = []
	texDict = {}
	with open(relPath + "artidx.mul", "rb") as fIdx, open(relPath + "art.mul", "rb") as fMul:
		while bs.getOffset() < bs.getSize():
			itemId = bs.readShort()
			blockNum = 16384 + itemId
			blockX = bs.readShort()
			blockY = bs.readShort()
			blockAltitude = bs.readShort()
			blockFlags = bs.readUInt()
			if UO_NEW_MULTI_VER:
				resv = bs.readUInt()

			tex = uoLoadArtTile(blockNum, texDict, fIdx, fMul)
			if tex:
				if itemId < len(staticData):
					itemData = staticData[itemId]
					tileFlags = itemData.flags
					tileHeight = itemData.height
				else:
					tileFlags = tileHeight = 0
				sort1 = (0 if tileHeight <= 0 else 1) + (0 if (tileFlags & UO_OBJFL_BACKGROUND) else 1)
				drawBlock = UODrawBlock(sort1, blockX, blockY, blockAltitude, blockFlags, itemId, tileHeight, tileFlags, tex, UO_DRAWTYPE_STATIC, 0, False)
				drawBlocks.append(drawBlock)
	loadArtTime = time.time() - loadArtStart

	if len(drawBlocks) == 0:
		return 0

	blockBlitStart = time.time()	
		
	imageData, canvasWidth, canvasHeight = uoDrawAllBlocks(drawBlocks)

	blockBlitTime = time.time()	- blockBlitStart
		
	tex = NoeTexture("uo_multi_tex", canvasWidth, canvasHeight, imageData, noesis.NOESISTEX_RGBA32)
	texList.append(tex)

	loadTotalTime = time.time() - loadStartTime
	
	print("Load complete.")
	print("Tile:", loadTileTime)
	print("Art:", loadArtTime)
	print("Draw:", blockBlitTime)
	print("Total:", loadTotalTime)
	
	return 1

def uoMapCheckType(data):
	if len(data) < 8:
		return 0
	bs = NoeBitStream(data)
	idxSize = bs.readUInt()
	dataSize = bs.readUInt()
	if len(data) != 8 + idxSize + dataSize:
		return 0
	return 1

def uoGetMapIndexFromFileName(baseName):
	mapNumberName = "0"
	mapIndex = 0
	mapIndexExpr = re.search("\d", baseName)
	if not mapIndexExpr:
		print("WARNING: Could not determine map index from filename.")
	else:
		numOfs = mapIndexExpr.start()
		mapIndex = int(baseName[numOfs])
		if mapIndex < 0 or mapIndex >= len(UO_MAP_HEIGHTS):
			print("WARNING: Map index from filename is out of known range, assuming 0.")
			mapIndex = 0
		else:
			#special case, preserve the x after the number
			copyCount = 2 if (numOfs + 1) < len(baseName) and baseName[numOfs + 1] == 'x' else 1
			mapNumberName = baseName[numOfs:numOfs + copyCount]
	return mapIndex, mapNumberName
	
def uoMapLoadRGBA(data, texList):
	bs = NoeBitStream(data)
	idxSize = bs.readUInt()
	dataSize = bs.readUInt()

	mapFileName = rapi.getLastCheckedName()
	relPath = findMulRelativeToFile(mapFileName, "radarcol.mul")
	if not relPath:
		return 0
	radarColors = rapi.loadIntoByteArray(relPath + "radarcol.mul")

	dataOfs = 8 + idxSize
	
	baseName = rapi.getLocalFileName(mapFileName).lower()
	mapIndex, mapNumberName = uoGetMapIndexFromFileName(baseName)
	mapHeight = UO_MAP_HEIGHTS[mapIndex]
	mapWidth = dataSize // 196 // mapHeight

	staticIdxData = None
	staticMulData = None
	
	#let's try to load the statics (optional)
	staticsIdxName = "staidx" + mapNumberName + ".mul"
	staticsMulName = "statics" + mapNumberName + ".mul"
	relPath = findMulRelativeToFile(mapFileName, staticsIdxName)
	if relPath:
		staticIdxData = rapi.loadIntoByteArray(relPath + staticsIdxName)
		staticMulData = rapi.loadIntoByteArray(relPath + staticsMulName)
	
	if noesis.optWasInvoked("-uomapterrain"): #rendered view
		fmt = noesis.optGetArg("-uomapterrain")
		values = [int(x) for x in fmt.split(";")]
		if len(values) == 4:
			landData, staticData = uoLoadTileData(rapi.getLastCheckedName())
			if len(landData) > 0 and len(staticData) > 0:			
				relPathArt = findMulRelativeToFile(rapi.getLastCheckedName(), "artidx.mul")
				relPathTex = findMulRelativeToFile(rapi.getLastCheckedName(), "texidx.mul")
				if relPathArt and relPathTex:
					landData, staticData = uoLoadTileData(rapi.getLastCheckedName())
					drawBlocks = []
					artDict = {}
					texDict = {}
					with open(relPathArt + "artidx.mul", "rb") as fArtIdx, open(relPathArt + "art.mul", "rb") as fArtMul:
						with open(relPathTex + "texidx.mul", "rb") as fTexIdx, open(relPathTex + "texmaps.mul", "rb") as fTexMul:
							loadX, loadY, loadW, loadH = values
							readFlags = UO_TERRAIN_READ_FLAGS
							#add land tiles
							cellData = rapi.callExtensionMethod("uo_map_read_cells_linear", data[dataOfs : dataOfs + dataSize], mapWidth, mapHeight, loadX, loadY, loadW, loadH, readFlags, UO_TERRAIN_NORMAL_XYSCALE, UO_TERRAIN_NORMAL_ZSCALE)
							cellBs = NoeBitStream(cellData)
							for y in range(0, loadH):
								for x in range(0, loadW):
									landId = cellBs.readUShort()
									landAlt = cellBs.readByte()
									landNCount = cellBs.readUByte()
									landNAlts = cellBs.readBytes(landNCount)
									landIsFlat = cellBs.readUByte() > 0
									landSortAlt = cellBs.readInt()
									landNormals = cellBs.readBytes(12 * 4) if readFlags & UO_CELLREAD_FLAG_NORMALS else None
									if landId < len(landData):
										landItem = landData[landId]
										isTextureMapped = landItem.texId > 0 and not landIsFlat
										tex = uoLoadArtTile(landItem.texId & 16383, texDict, fTexIdx, fTexMul, True) if isTextureMapped else uoLoadArtTile(landId, artDict, fArtIdx, fArtMul)
										if tex:
											drawBlock = UODrawBlock(0, x, y, landAlt, 0, landId, 0, 0, tex, UO_DRAWTYPE_LAND, 0, isTextureMapped)
											drawBlock.terrainAltitude = landSortAlt
											drawBlock.terrainNormals = landNormals
											drawBlock.setNeighborData(landNAlts)
											drawBlocks.append(drawBlock)
							#add static tiles
							if staticIdxData and staticMulData:
								for blockY in range(loadY // 8, (loadY + loadH + 7) // 8):
									for blockX in range(loadX // 8, (loadX + loadW + 7) // 8):
										staticIndexOffset = (blockX * mapHeight + blockY) * 12
										if staticIndexOffset < len(staticIdxData):
											staticsOfs, staticsSize = noeUnpack("<II", staticIdxData[staticIndexOffset : staticIndexOffset + 8])
											if staticsOfs != 0xFFFFFFFF and staticsSize != 0xFFFFFFFF and staticsSize > 0:
												staticCount = staticsSize // 7
												for staticIndex in range(0, staticCount):
													staticOfs = staticsOfs + staticIndex * 7
													staticId, staticPosX, staticPosY, staticAlt = noeUnpack("<HBBb", staticMulData[staticOfs : staticOfs + 5])
													tex = uoLoadArtTile(16384 + staticId, artDict, fArtIdx, fArtMul)
													if tex:													
														x = (blockX * 8 + (staticPosX & 7)) - loadX
														y = (blockY * 8 + (staticPosY & 7)) - loadY
														if x >= 0 and y >= 0 and x < loadW and y < loadH: #ignore anything off the end of the load area, since the load area may not be block-aligned
															if staticId < len(staticData):
																itemData = staticData[staticId]
																tileFlags = itemData.flags
																tileHeight = itemData.height
															else:
																tileFlags = tileHeight = 0														
															sort1 = (0 if tileHeight <= 0 else 1) + (0 if (tileFlags & UO_OBJFL_BACKGROUND) else 1)
															drawBlock = UODrawBlock(sort1, x, y, staticAlt, 0, staticId, tileHeight, tileFlags, tex, UO_DRAWTYPE_STATIC, staticIndex, False)
															drawBlocks.append(drawBlock)
					#now use the noesis software renderer to pre-render terrain blocks as necessary
					rapi.callExtensionMethod("uo_map_generate_terrain_data", drawBlocks, UO_TERRAIN_BLOCK_WIDTH, UO_TERRAIN_BLOCK_HEIGHT, data[dataOfs : dataOfs + dataSize], mapWidth, mapHeight, loadX, loadY, UO_TERRAIN_LIGHT_DIR, UO_TERRAIN_LIGHT_AMBIENT, UO_TERRAIN_LIGHT_DIRECT)
					imageData, canvasWidth, canvasHeight = uoDrawAllBlocks(drawBlocks)
					if len(imageData) > 0:
						tex = NoeTexture("uo_map_tex", canvasWidth, canvasHeight, imageData, noesis.NOESISTEX_RGBA32)
						texList.append(tex)
					else:
						print("Warning: No renderable data could be located within the specified region.")
				else:
					print("Warning: Can't render terrain without art and tex data.")
			else:
				print("Warning: Can't render terrain without land data.")
		else:
			print("Warning: Bad formatting on argument:", fmt)
	else: #radar view
		imageWidth = mapWidth * 8
		imageHeight = mapHeight * 8
		#this is broken out into a native extension, because it just takes too long to do in python despite its simplicity.
		#the 4 parameters before static data are to allow rendering a sub-region of the map, if desired.
		imageData = rapi.callExtensionMethod("uo_map_render_radar", data[dataOfs : dataOfs + dataSize], radarColors, mapWidth, mapHeight, 0, 0, mapWidth, mapHeight, staticIdxData, staticMulData)
		
		rgbaData = rapi.imageDecodeRaw(imageData, imageWidth, imageHeight, "b5g5r5p1")
		tex = NoeTexture("uo_map_tex", imageWidth, imageHeight, rgbaData, noesis.NOESISTEX_RGBA32)
		texList.append(tex)

	return 1
