from inc_noesis import *
from inc_romcom import *

def registerNoesisTypes():
	handle = noesis.registerTool("Batman Forever: TAG Raw Dump", batRawDumpToolMethod, "Dump Batman Forever: TAG data in proper source (deinterleaved, endian swapped) form.")
	handle = noesis.registerTool("Batman Forever: TAG Sprite Dump", batSprDumpToolMethod, "Dump Batman Forever: TAG sprites.")
	return 1

BFTAG_CodeImageSize = 1024 * 1024
BFTAG_CodeImages = ("350-mpa1.u19", "350-mpa1.u16")
BFTAG_GfxImageSize = 4096 * 1024
BFTAG_GfxImages = ("gfx0.u1", "gfx1.u3", "gfx2.u5", "gfx3.u8", "gfx4.u12", "gfx5.u15", "gfx6.u18")

BFTAG_EnemyInfoPtrOffset = 0xA8E2C
BFTAG_MaxModeCount = 256

BFTAG_GfxBatPalOffset = 0xCC99CC
BFTAG_BatModePtrOffset = 0x1A6440
BFTAG_GfxRobinPalOffset = 0xCC9CCC
BFTAG_RobinModePtrOffset = 0x1A490C
BFTAG_GfxRiddlerPalOffset = 0xCCED0C
BFTAG_RiddlerModePtrOffset = 0x1ABFFC

def batGameOvlAddrToFile(addr):
	if addr == 0:
		return 0
	if addr >= 0x22200000:
		return addr - 0x22200000
	return addr - 0x5FD31A4
	
def batGfxAddrToFile(addr):
	if addr == 0:
		return 0
	return addr - 0x22400000
	
def batIsValidGameAddr(addr):
	if addr == 0:
		return True
	if addr >= 0x22200000:
		return addr < 0x22400000
	return addr >= 0x06011000 and addr < 0x07000000

def batIsValidGfxAddr(addr):
	if addr == 0:
		return True
	return addr >= 0x22400000 and addr < 0x30000000
	
class BatInfoTable:
	def __init__(self, bs):
		self.setupOffset = batGameOvlAddrToFile(bs.readUInt())
		self.fxPalOffset = batGameOvlAddrToFile(bs.readUInt())
		self.statsOffset = batGameOvlAddrToFile(bs.readUInt())
		self.scriptOffset = batGameOvlAddrToFile(bs.readUInt())
		
class BatSetupTable:
	def __init__(self, bs):
		self.modeTableOffset = batGameOvlAddrToFile(bs.readUInt())
		self.defaultMode = bs.readShort()
		self.slots = bs.readShort()
		self.specialSetupAddr = bs.readUInt()
		self.updateAddr = bs.readUInt()
		self.hitPlayerAddr = bs.readUInt()
		self.hitEnemyAddr = bs.readUInt()
		self.hitObjectAddr = bs.readUInt()
		self.playerHitAddr = bs.readUInt()
		self.shockHitAddr = bs.readUInt()
		self.weapHitAddr = bs.readUInt()
		self.unHitAddr = bs.readUInt()
		self.bboxAddr = bs.readUInt()
		self.mass = bs.readUInt()
		
class BatFxPal:
	def __init__(self, bs):
		self.palGfxOffset = batGfxAddrToFile(bs.readUInt())
		self.palCount = bs.readUInt()
		#ignore the rest
	
class BatSprite:
	def __init__(self, bs):
		self.offset = bs.tell() + bs.readUInt()
		self.decompSize = bs.readUInt()
		self.compSize = bs.readUInt()
		self.width = bs.readUInt()
		self.height = bs.readUInt()
		self.ox = -bs.readInt()
		self.oy = -bs.readInt()
		self.rx = bs.readInt()
		self.ry = bs.readInt()
		self.ax = bs.readInt()
		self.ay = bs.readInt()
		self.bx = bs.readInt()
		self.by = bs.readInt()
		#hop to end in case we'd like to continue reading contiguously
		bs.seek((self.compSize + 3) & ~3, NOESEEK_REL)
		
	def getMinMax(self):
		return self.ox, self.oy, self.ox + self.width, self.oy + self.height
		
	def decompress(self, bs, pal):
		bs.seek(self.offset, NOESEEK_ABS)
		data = bs.readBytes(self.compSize)
		decompData = rapi.callExtensionMethod("bftag_decomp", data, self.decompSize)
		return rapi.imageDecodeRawPal(decompData, pal, self.width, self.height, 8, "r8g8b8a8")

def batLoadData(imageBasePath):
	print("Loading ROM images.")
	codeData = readRomImages(imageBasePath, BFTAG_CodeImages, BFTAG_CodeImageSize, ReadRomImageFlag_Interleave)		
	gfxData = readRomImages(imageBasePath, BFTAG_GfxImages, BFTAG_GfxImageSize, ReadRomImageFlag_EndianSwap_Word)
	return codeData, gfxData
	
def batRawDump(imageBasePath):
	codeData, gfxData = batLoadData(imageBasePath)
	if not codeData or not gfxData:
		return -1

	print("Writing code_raw.bin")
	with open(os.path.join(imageBasePath, "code_raw.bin"), "wb") as f:
		f.write(codeData)
	print("Writing gfx_raw.bin")
	with open(os.path.join(imageBasePath, "gfx_raw.bin"), "wb") as f:
		f.write(gfxData)
	
	return 0
	
def batFrameBounds(frames):
	minX, minY, maxX, maxY = frames[0].getMinMax()
	for i in range(1, len(frames)):
		fminX, fminY, fmaxX, fmaxY = frames[i].getMinMax()
		minX = min(minX, fminX)
		minY = min(minY, fminY)
		maxX = max(maxX, fmaxX)
		maxY = max(maxY, fmaxY)
	return minX, minY, maxX, maxY

def batExportFrames(frames, palData, gfxBs, name, outDir):
	minX, minY, maxX, maxY = batFrameBounds(frames)
	canvasWidth = maxX - minX
	canvasHeight = maxY - minY
	
	textures = []
	for frame in frames:
		rgba = frame.decompress(gfxBs, palData)
		canvasRgba = bytearray(canvasWidth * canvasHeight * 4)
		fminX, fminY, fmaxX, fmaxY = frame.getMinMax()		
		rapi.imageBlit32(canvasRgba, canvasWidth, canvasHeight, fminX - minX, fminY - minY, rgba, frame.width, frame.height, 0, 0, 0, 0, noesis.BLITFLAG_ALPHABLEND)
		tex = NoeTexture("bmframe", canvasWidth, canvasHeight, canvasRgba, noesis.NOESISTEX_RGBA32)
		textures.append(tex)
	
	texName = os.path.join(outDir, name)
	noesis.saveImageRGBA(texName, textures)
	
def batDumpModeTable(codeBs, gfxBs, modeTableOffset, palGfxOffset, namePrefix, outDir):
	animEntries = []
	codeBs.seek(modeTableOffset, NOESEEK_ABS)
	for modeIndex in range(0, BFTAG_MaxModeCount):
		setupAddr = codeBs.readUInt()
		codeAddr = codeBs.readUInt()
		#no explicit mode count, so we're doing some sloppy range/value checking to break out when we hit bad data
		if not batIsValidGameAddr(setupAddr) or not batIsValidGameAddr(codeAddr):
			break
		animOffset = batGameOvlAddrToFile(codeBs.readUInt())
		speed = codeBs.readUInt()
		if animOffset > 0:
			if animOffset not in animEntries: #don't care about dups
				animEntries.append(animOffset)
		elif animOffset < 0 or speed > 0x00FF0000:
			break

	if len(animEntries) > 0:
		gfxBs.seek(palGfxOffset, NOESEEK_ABS)
		#just read over number of colors, extra data will be unreferenced
		palData = gfxBs.readBytes(768)
		#expand to rgba and mark pal0 transparent
		palData = rapi.imageDecodeRaw(palData, 256, 1, "r8g8b8")
		palData[3] = 0
		
		for animIndex in range(0, len(animEntries)):
			animOffset = animEntries[animIndex]
			codeBs.seek(animOffset, NOESEEK_ABS)
			frames = []
			while True:
				gfxOffset = codeBs.readInt()
				if gfxOffset <= 0 or not batIsValidGfxAddr(gfxOffset): #0=loop, <0=back up n frames (where -1 means hold on the last frame)
					break
				codeBs.readInt() #unused
				codeBs.readInt() #unused
				gfxBs.seek(batGfxAddrToFile(gfxOffset))
				frame = BatSprite(gfxBs)							
				frames.append(frame)
				
			if len(frames) > 0:
				name = namePrefix + "_anim%02i.gif"%animIndex
				batExportFrames(frames, palData, gfxBs, name, outDir)

def batSprDump(imageBasePath):	
	codeData, gfxData = batLoadData(imageBasePath)
	if not codeData or not gfxData:
		return -1

	outDir = os.path.join(imageBasePath, "noesis_gfxdump")
	if not os.path.exists(outDir):
		os.makedirs(outDir)
		
	codeBs = NoeBitStream(codeData, NOE_BIGENDIAN)
	gfxBs = NoeBitStream(gfxData, NOE_BIGENDIAN)

	#first dump special cases
	print("Exporting frames for Batman.")
	batDumpModeTable(codeBs, gfxBs, BFTAG_BatModePtrOffset, BFTAG_GfxBatPalOffset, "batman", outDir)	
	print("Exporting frames for Robin.")
	batDumpModeTable(codeBs, gfxBs, BFTAG_RobinModePtrOffset, BFTAG_GfxRobinPalOffset, "robin", outDir)	
	print("Exporting frames for Riddler.")
	batDumpModeTable(codeBs, gfxBs, BFTAG_RiddlerModePtrOffset, BFTAG_GfxRiddlerPalOffset, "riddler", outDir)
	
	#possible todo - track down other mode tables

	#now dump enemies from the info pointer
	codeBs.seek(BFTAG_EnemyInfoPtrOffset, NOESEEK_ABS)
	infoPtrs = []
	while True:
		infoPtr = codeBs.readUInt()
		if not batIsValidGameAddr(infoPtr) or infoPtr == 0:
			break
		infoPtrs.append(batGameOvlAddrToFile(infoPtr))

	enemyInfos = []
	for infoPtr in infoPtrs:
		codeBs.seek(infoPtr, NOESEEK_ABS)
		info = BatInfoTable(codeBs)
		enemyInfos.append(info)
		
	print("Parsed", len(enemyInfos), "enemy info tables.")
	
	for enemyIndex in range(0, len(enemyInfos)):
		print("Exporting frames for enemy", enemyIndex)
		info = enemyInfos[enemyIndex]
		if info.setupOffset > 0 and info.fxPalOffset:
			codeBs.seek(info.fxPalOffset, NOESEEK_ABS)
			fxPal = BatFxPal(codeBs)		
			codeBs.seek(info.setupOffset, NOESEEK_ABS)
			setupTable = BatSetupTable(codeBs)
			
			if setupTable.modeTableOffset > 0:
				batDumpModeTable(codeBs, gfxBs, setupTable.modeTableOffset, fxPal.palGfxOffset, "enemy%02i"%enemyIndex, outDir)
		
	print("Finished dump to", outDir)
		
	return 0
		
def batGenericToolMethod(dumpMethod):
	imageBasePath = noesis.userPrompt(noesis.NOEUSERVAL_FOLDERPATH, "Load Image", "Select location of ROM data.", noesis.getSelectedDirectory(), None)
	if not imageBasePath:
		return 0

	noesis.logPopup()
		
	noeMod = noesis.instantiateModule()
	noesis.setModuleRAPI(noeMod)
		
	r = dumpMethod(imageBasePath)

	noesis.freeModule(noeMod)
	
	return r

def batRawDumpToolMethod(toolIndex):
	return batGenericToolMethod(batRawDump)

def batSprDumpToolMethod(toolIndex):
	return batGenericToolMethod(batSprDump)
