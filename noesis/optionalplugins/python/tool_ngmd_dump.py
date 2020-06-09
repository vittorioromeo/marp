from inc_noesis import *
import os

#this script is intended to be used with the Ninja Gaiden Genesis prototype.
#offsets may or may not match up across prototype dumps in the wild, i've only been able to test one of them.

NG_LEVEL_COMPOSITE = False
NG_DUMP_BG_CHARS = False #useful for getting animated tiles, since the game uses a table of functions with hardcoded addresses to do cutscene anims.
NG_GRAB_BG_EXTRA = True
NG_IMAGE_OUT = ".png"
NG_IMAGE_ANIM_OUT = ".gif"
NG_RAW_CHARS_WIDTH = 16

def registerNoesisTypes():
	#sprite dump uses the actual move tables, which means there are lots of duplicates (for stubbed in entries) and re-used parts/frames.
	handle = noesis.registerTool("Ninja Gaiden (Genesis) - Sprite Dump", sprDumpToolMethod, "Dump sprites from NG MD ROM.")
	noesis.setToolFlags(handle, noesis.NTOOLFLAG_CONTEXTITEM)
	noesis.setToolVisibleCallback(handle, ngDumpContextVisible)

	handle = noesis.registerTool("Ninja Gaiden (Genesis) - Background Dump", bkgDumpToolMethod, "Dump backgrounds from NG MD ROM.")
	noesis.setToolFlags(handle, noesis.NTOOLFLAG_CONTEXTITEM)
	noesis.setToolVisibleCallback(handle, ngDumpContextVisible)
	
	return 1

def ngValidateRom(path):
	try:
		with open(path, "rb") as f:
			f.seek(0x100, os.SEEK_SET) #assume headerless image
			segaId = f.read(4)
			if segaId == "SEGA".encode("ASCII"):
				f.seek(0x150, os.SEEK_SET)
				gameId = f.read(12)
				if gameId == "ARM WRESTLIN".encode("ASCII") or gameId == "NINJA GAIDEN".encode("ASCII"): #segaretro rom has garbage title, incorrect rom size, etc.
					return True
	except:
		pass
	return False

def ngDumpContextVisible(toolIndex, selectedFile):
	if not selectedFile:
		return 0
	nameNoExt, ext = os.path.splitext(selectedFile)
	ext = ext.lower()
	if ext != ".bin" and ext != ".md":
		return 0
	if ngValidateRom(selectedFile):
		return 1
	return 0

DumpFlag_Sprites = (1 << 0)
DumpFlag_Levels = (1 << 1)
DumpFlag_Cutscenes = (1 << 2)

SetFlag_None = 0
SetFlag_DmaParts = (1 << 0)
SetFlag_Enemy = (1 << 1)
SetFlag_Boss = (1 << 2)
SetFlag_EmbeddedPalette = (1 << 3)

Gen_PalSize = 2 * 16

#these are values which may vary across builds
NgRom_RyuSet = 0xE0000
NgRom_BossSet = 0xB0000
NgRom_EnemySet = 0x30000
NgRom_EnvObjChars = 0x11346 - 0xA000 #relevant char data is at 0x11346, but we're offsetting here for convenience so that the vram offsets line up. (it's loaded into vram 0xA000)
NgRom_MiscChars = 0x10646 - 0xD000 #similar to above, loaded at vram 0xD000
NgRom_EnvPals = (0x7CC7C, 0x81520, 0xE1B9A, 0x3008C)
NgRom_EnvObjCount = 3
NgRom_MaxEnemyBossAnimCount = 19
NgRom_Levels = 0x80000
NgRom_Cutscenes = 0x60000
NgRom_CutsceneLevelIndices = (19, 20, 28) #treat these entries in the cutscene table as levels
#there's no data-driven mechanism to specify tile mirroring, so this is handled manually.
NgRom_TileMirrorRects = { 14 : ((57, 4, 60, 11),) }

def getMirrorFlags(mirrorRects, x, y):
	if mirrorRects:
		for minX, minY, maxX, maxY in mirrorRects:
			if x >= minX and x <= maxX and y >= minY and y <= maxY:
				return 8
	return 0

def calcMinMax(objList):
	obj = objList[0]
	minX = obj.offsetX
	minY = obj.offsetY
	maxX = obj.offsetX + obj.width
	maxY = obj.offsetY + obj.height
	for i in range(1, len(objList)):
		obj = objList[i]
		minX = min(minX, obj.offsetX)
		minY = min(minY, obj.offsetY)
		maxX = max(maxX, obj.offsetX + obj.width)
		maxY = max(maxY, obj.offsetY + obj.height)
	return minX, minY, maxX, maxY

def decompFromAddress(bs, addr):
	if addr == 0:
		return None
	bs.seek(addr, NOESEEK_ABS)
	#sizes are packed as little-endian
	totalSize, srcSize = noeUnpack("<HH", bs.readBytes(4))
	return rapi.callExtensionMethod("ngmd_decomp", bs.readBytes(srcSize))	
	
def loadSetAddresses(setAddrs, bs, baseAddr, setFlags):
	bs.seek(baseAddr, NOESEEK_ABS)
	firstAddr = bs.readInt()
	setAddrs.append((firstAddr, setFlags))
	while bs.tell() < firstAddr:
		addr = bs.readInt()
		setAddrs.append((addr, setFlags))

class NgPart:
	def __init__(self, bs, setFlags):
		self.offsetY = bs.readByte()
		tileSize = bs.readUByte()
		self.widthInTiles = 1 + ((tileSize >> 2) & 3)
		self.heightInTiles = 1 + (tileSize & 3)
		self.width = self.widthInTiles * 8
		self.height = self.heightInTiles * 8
		if setFlags & SetFlag_DmaParts:
			self.spriteOffset = bs.readUShort()
			self.vm = bs.readUShort()
		else:
			#these guys have their entire tileset blasted into vram at once, so translate the tile index to an offset
			self.vm = bs.readUShort()
			self.spriteOffset = (self.vm & 0x7FF) << 5
		self.offsetX = bs.readByte()
		self.u0 = bs.readByte()
		
	def loadTiles(self, bs, charBaseAddr):
		tileCount = self.widthInTiles * self.heightInTiles
		bs.seek(charBaseAddr + self.spriteOffset, NOESEEK_ABS)
		self.charData = bs.readBytes(tileCount << 5)
		
	def writeToCharStream(self, charBs):
		self.tileOffset = charBs.tell()
		charBs.writeBytes(self.charData)

class NgFrame:
	def __init__(self, bs, setFlags):
		self.partAddr = bs.readInt()
		self.u0 = bs.readUShort()
		self.u1 = bs.readUShort()
		self.u2 = bs.readUByte()
		self.u3 = bs.readUByte()
		self.u4 = bs.readInt()
		self.u5 = bs.readInt()
		self.u6 = bs.readInt()
		self.parts = []
		bs.seek(self.partAddr, NOESEEK_ABS)
		partCount = bs.readUByte() + 1
		bs.readUByte() #unused
		for i in range(0, partCount):
			part = NgPart(bs, setFlags)
			self.parts.append(part)
		minX, minY, maxX, maxY = calcMinMax(self.parts)
		self.offsetX = minX
		self.offsetY = minY
		self.width = (maxX - minX)
		self.height = (maxY - minY)
		self.setFlags = setFlags
			
	def loadTiles(self, bs, charBaseAddr):
		for part in self.parts:
			part.loadTiles(bs, charBaseAddr)
			
	def drawToCanvas(self, canvRgba, charBs, palData, canvWidth, canvHeight, ulX, ulY, drawFlags):
		charBs.seek(0, NOESEEK_ABS)
		for part in self.parts:
			part.writeToCharStream(charBs)
			
		for partIndex in range(0, len(self.parts)):
			part = self.parts[len(self.parts) - partIndex - 1]
			offsetX = part.offsetX - ulX
			offsetY = part.offsetY - ulY
			vmMask = 0x1800 #grab the flip bits
			if self.setFlags & SetFlag_EmbeddedPalette:
				vmMask |= 0x6000 #preserve palette bits too
			tileData = (part.vm & vmMask) >> 8
			rapi.callExtensionMethod("vdp_drawtile_rgba", canvRgba, canvWidth, canvHeight, offsetX, offsetY, tileData, charBs.getBuffer()[part.tileOffset:], palData, drawFlags, part.widthInTiles, part.heightInTiles)
	
class NgLevel:
	def __init__(self, bs):
		self.charsAddr = bs.readInt()
		self.palAddr = bs.readInt()
		self.bgAddr = bs.readInt()
		self.fgAddr = bs.readInt()
		self.width = bs.readUShort()
		self.height = bs.readUShort()
		self.u2 = bs.readInt()
		self.u3 = bs.readInt()
		self.u4 = bs.readInt()
		
	def isValid(self):
		return self.charsAddr != 0 and self.width > 0 and self.height > 0

class NgCutscene:
	def __init__(self, bs):
		self.map0Addr = bs.readInt()
		self.map1Addr = bs.readInt()
		self.charsAddrs = (bs.readInt(), bs.readInt(), bs.readInt(), bs.readInt())
		self.palAddrs = (bs.readInt(), bs.readInt(), bs.readInt(), bs.readInt())
		
def ngDumpRawTiles(binName, charData, tileWidth, tileHeight, charName, palData, palIndex, drawFlags):
	texWidth = tileWidth << 3
	texHeight = tileHeight << 3
	rgba = bytearray(texWidth * texHeight * 4)
	for y in range(0, tileHeight):
		for x in range(0, tileWidth):
			tileIndex = y * tileWidth + x
			tileData = tileIndex | (palIndex << 13)
			rapi.callExtensionMethod("vdp_drawtile_rgba", rgba, texWidth, texHeight, x << 3, y << 3, (tileData >> 8) | ((tileIndex & 0xFF) << 8), charData, palData, drawFlags & ~1)
	name = os.path.splitext(binName)[0] + charName + NG_IMAGE_OUT
	print("Writing", name)
	noesis.saveImageRGBA(name, NoeTexture(name, texWidth, texHeight, rgba, noesis.NOESISTEX_RGBA32))

def ngDumpLevel(bs, binName, levelName, level, levelIndex, drawFlags):
	texWidth = level.width << 3
	texHeight = level.height << 3
	
	bs.seek(level.palAddr, NOESEEK_ABS)
	palData = bs.readBytes(Gen_PalSize * 4)
	
	charData = decompFromAddress(bs, level.charsAddr)
	mapDatas = ((decompFromAddress(bs, level.bgAddr), drawFlags), (decompFromAddress(bs, level.fgAddr), drawFlags & ~1))
	
	mirrorRects = NgRom_TileMirrorRects.get(levelIndex)
	
	if NG_DUMP_BG_CHARS:
		charsName = levelName + ".chars"
		charsWidth = NG_RAW_CHARS_WIDTH
		charsHeight = len(charData) // charsWidth // 32
		ngDumpRawTiles(binName, charData, charsWidth, charsHeight, charsName, palData, 0, drawFlags)
	
	if NG_LEVEL_COMPOSITE:
		rgba = bytearray(texWidth * texHeight * 4)
		for mapIndex in range(0, len(mapDatas)):
			mapData, mapDrawFlags = mapDatas[len(mapDatas) - mapIndex - 1]
							
			mapBs = NoeBitStream(mapData)
			for y in range(0, level.height):
				for x in range(0, level.width):
					tileIndex = mapBs.readUByte()
					tileData = (tileIndex << 8) | getMirrorFlags(mirrorRects, x, y)
					rapi.callExtensionMethod("vdp_drawtile_rgba", rgba, texWidth, texHeight, x << 3, y << 3, tileData, charData, palData, mapDrawFlags)
		name = os.path.splitext(binName)[0] + levelName + NG_IMAGE_OUT
		print("Writing", name)
		noesis.saveImageRGBA(name, NoeTexture(name, texWidth, texHeight, rgba, noesis.NOESISTEX_RGBA32))
	else:
		for mapIndex in range(0, len(mapDatas)):
			mapData, mapDrawFlags = mapDatas[mapIndex]
			rgba = bytearray(texWidth * texHeight * 4)
							
			mapBs = NoeBitStream(mapData)
			for y in range(0, level.height):
				for x in range(0, level.width):
					tileIndex = mapBs.readUByte()
					tileData = (tileIndex << 8) | getMirrorFlags(mirrorRects, x, y)
					rapi.callExtensionMethod("vdp_drawtile_rgba", rgba, texWidth, texHeight, x << 3, y << 3, tileData, charData, palData, mapDrawFlags)
			name = os.path.splitext(binName)[0] + levelName + ".layer%02i"%mapIndex + NG_IMAGE_OUT
			print("Writing", name)
			noesis.saveImageRGBA(name, NoeTexture(name, texWidth, texHeight, rgba, noesis.NOESISTEX_RGBA32))

def ngDump(dumpFlags):
	noesis.logPopup()

	binName = noesis.getSelectedFile()
	if not binName or not os.path.exists(binName):
		noesis.messagePrompt("Selected file isn't readable through the standard filesystem.")
		return 0

	noeMod = noesis.instantiateModule()
	noesis.setModuleRAPI(noeMod)
	
	colorRampIndex = 6
	drawFlags = 1 | (colorRampIndex << 24)
	
	with open(binName, "rb") as f:
		#screw it, just stuff the whole thing in a stream
		bs = NoeBitStream(f.read(), NOE_BIGENDIAN)
		endOfROM = bs.getSize()

		if dumpFlags & DumpFlag_Sprites:
			#start with ryu, who's special-cased to use the DmaParts flag
			setAddrs = [(NgRom_RyuSet, SetFlag_DmaParts)]
			loadSetAddresses(setAddrs, bs, NgRom_BossSet, SetFlag_Boss) #bosses
			loadSetAddresses(setAddrs, bs, NgRom_EnemySet, SetFlag_Enemy) #enemies
			
			embPalCount = 0
			for setIndex in range(0, len(setAddrs)):
				setBase, setFlags = setAddrs[setIndex]
				bs.seek(setBase, NOESEEK_ABS)
				palAddr = bs.readInt()
				animsAddr = bs.readInt()
				charBaseAddr = bs.readInt()
				if palAddr == animsAddr:
					setFlags |= SetFlag_EmbeddedPalette
					#special case for all of these objects, game hardcodes address.
					charBaseAddr = NgRom_EnvObjChars if embPalCount < NgRom_EnvObjCount else NgRom_MiscChars
					embPalCount += 1
					
				if setFlags & SetFlag_EmbeddedPalette:
					palData = bytearray()
					for envPalAddr in NgRom_EnvPals:
						bs.seek(envPalAddr, NOESEEK_ABS)
						palData += bs.readBytes(Gen_PalSize)
				else:
					bs.seek(palAddr, NOESEEK_ABS)
					palData = bs.readBytes(Gen_PalSize * 4) #just overread since only pal0 will be used
				
				maxAnimCount = NgRom_MaxEnemyBossAnimCount if setFlags & (SetFlag_Boss | SetFlag_Enemy) else 0x1000
				animOffsets = []
				bs.seek(animsAddr, NOESEEK_ABS)
				while len(animOffsets) < maxAnimCount:
					animOffset = bs.readInt()
					if animOffset == 0:
						break
					animOffsets.append(animOffset)
				
				for animIndex in range(0, len(animOffsets)):
					framesAddr = animOffsets[animIndex]
					bs.seek(framesAddr, NOESEEK_ABS)
					frameOffsets = []
					while True:
						frameOffset = bs.readInt()
						if frameOffset == 0:
							break
						elif frameOffset < setBase or frameOffset >= endOfROM or (frameOffset & 0xFF0000) != (setBase & 0xFF0000):
							frameOffsets = [] #not a raw frame list, abort
							break
						frameOffsets.append(frameOffset)
				
					if len(frameOffsets) == 0:
						break
						
					frames = []
					for frameOffset in frameOffsets:
						bs.seek(frameOffset, NOESEEK_ABS)
						frame = NgFrame(bs, setFlags)
						frame.loadTiles(bs, charBaseAddr)
						frames.append(frame)
					
					minX, minY, maxX, maxY = calcMinMax(frames)
					canvWidth = maxX - minX
					canvHeight = maxY - minY
					charBs = NoeBitStream(bytes(0x10000))
					textures = []
					animName = "set%03i.anim%03i"%(setIndex, animIndex)
					for frameIndex in range(0, len(frames)):
						frame = frames[frameIndex]
						canvRgba = bytearray(canvWidth * canvHeight * 4)
						frame.drawToCanvas(canvRgba, charBs, palData, canvWidth, canvHeight, minX, minY, drawFlags)
						textures.append(NoeTexture(animName + ".frame%03i"%(frameIndex), canvWidth, canvHeight, canvRgba, noesis.NOESISTEX_RGBA32))
					name = os.path.splitext(binName)[0] + "." + animName + NG_IMAGE_ANIM_OUT
					print("Writing", name)
					noesis.saveImageRGBA(name, textures)
		
		if dumpFlags & DumpFlag_Levels:
			bs.seek(NgRom_Levels, NOESEEK_ABS)
			levels = []
			while bs.tell() < endOfROM:
				level = NgLevel(bs)
				if not level.isValid():
					break
				levels.append(level)
			print("Found", len(levels), "levels.")

			for levelIndex in range(0, len(levels)):
				level = levels[levelIndex]
				levelName = ".level%02i"%levelIndex
				ngDumpLevel(bs, binName, levelName, level, levelIndex, drawFlags)

		if dumpFlags & DumpFlag_Cutscenes:
			bs.seek(NgRom_Cutscenes, NOESEEK_ABS)
			csAddrs = []
			while bs.tell() < endOfROM:
				addr = bs.readInt()
				if addr == 0:
					break
				csAddrs.append(addr)
			print("Found", len(csAddrs), "cutscenes.")
				
			for sceneIndex in range(0, len(csAddrs)):
				bs.seek(csAddrs[sceneIndex], NOESEEK_ABS)
				csName = ".cs%02i"%sceneIndex
				if sceneIndex in NgRom_CutsceneLevelIndices:
					level = NgLevel(bs)
					if level.isValid():
						ngDumpLevel(bs, binName, csName, level, -1, drawFlags)
				else:
					cs = NgCutscene(bs)
					mapDatas = (decompFromAddress(bs, cs.map0Addr), decompFromAddress(bs, cs.map1Addr))

					palData = bytearray(Gen_PalSize * 4)
					for palIndex in range(0, len(cs.palAddrs)):
						palAddr = cs.palAddrs[palIndex]
						if palAddr:
							bs.seek(palAddr, NOESEEK_ABS)
							palOffset = palIndex * Gen_PalSize
							palData[palOffset : palOffset + Gen_PalSize] = bs.readBytes(Gen_PalSize)

					charData = bytearray()
					for charsIndex in range(0, len(cs.charsAddrs)):
						charsAddr = cs.charsAddrs[charsIndex]
						if charsAddr:
							charDecomp = decompFromAddress(bs, charsAddr)
							if NG_DUMP_BG_CHARS:
								charsName = csName + ".chars%02i"%charsIndex
								charsWidth = NG_RAW_CHARS_WIDTH
								charsHeight = len(charDecomp) // charsWidth // 32
								#palette set isn't always 1:1 with char set - special-case here if you care
								ngDumpRawTiles(binName, charDecomp, charsWidth, charsHeight, charsName, palData, charsIndex, drawFlags)
							charData += charDecomp

					for mapIndex in range(0, len(mapDatas)):
						mapData = mapDatas[mapIndex]
						if mapData:						
							mapBs = NoeBitStream(mapData, NOE_BIGENDIAN)
							mapU0 = mapBs.readInt()
							tileWidth = mapBs.readUShort()
							tileHeight = mapBs.readUShort()
							if tileWidth > 0 and tileHeight > 0:
								if NG_GRAB_BG_EXTRA:
									#additional tiles are often packed onto the end.
									#some pack the above header in as well, but we're not bothering to differentiate.
									rowSize = tileWidth * 2
									tileHeight = (len(mapData) - 8) // rowSize
								texWidth = tileWidth << 3
								texHeight = tileHeight << 3
								rgba = bytearray(texWidth * texHeight * 4)
								for y in range(0, tileHeight):
									for x in range(0, tileWidth):
										#preserve big-endian order for tile
										tileData = mapBs.readUByte() | (mapBs.readUByte() << 8)
										rapi.callExtensionMethod("vdp_drawtile_rgba", rgba, texWidth, texHeight, x << 3, y << 3, tileData, charData, palData, drawFlags & ~1)
								name = os.path.splitext(binName)[0] + csName + ".layer%02i"%mapIndex + NG_IMAGE_OUT
								print("Writing", name)
								noesis.saveImageRGBA(name, NoeTexture(name, texWidth, texHeight, rgba, noesis.NOESISTEX_RGBA32))
		
	noesis.freeModule(noeMod)

	return 0
	
def sprDumpToolMethod(toolIndex):
	return ngDump(DumpFlag_Sprites)
	
def bkgDumpToolMethod(toolIndex):
	return ngDump(DumpFlag_Levels | DumpFlag_Cutscenes)
