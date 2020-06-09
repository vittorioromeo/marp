from inc_noesis import *
from inc_romcom import snesLoRomPtrToFileOffset
import os

#these tables are padded out which normally helps them stay at fixed locations.
#however, earlier versions of the game use drastically different data structures (and in some cases pad pointers to 4 bytes), which means this script won't work with them.
PALETTE_TABLE_ADDRESS = 0x808040
FRAME_TABLE_ADDRESS = 0x808400
BG_TABLE_ADDRESS = 0x809380

COLLISION_LUT_ADDRESS = 0x81948B
COLLISION_TILES_ADDRESS = 0x81931B

#bg options
DRAW_COLLISION = False
DUMP_RAW_BINARIES = False

#frame options
FIXED_CANVAS_SIZE = None #(320, 240)
USE_SINGLE_FILE = False #probably want to use FIXED_CANVAS_SIZE too if enabling this

TEST_DUMP_LIST = []

def registerNoesisTypes():
	handle = noesis.registerTool("Fireteam Rogue (SNES) - Background Dump", rogueBgDumpToolMethod, "Dump backgrounds from Fireteam Rogue ROM.")
	noesis.setToolFlags(handle, noesis.NTOOLFLAG_CONTEXTITEM)
	noesis.setToolVisibleCallback(handle, rogueDumpContextVisible)

	handle = noesis.registerTool("Fireteam Rogue (SNES) - Frame Dump", rogueFrameDumpToolMethod, "Dump frames from Fireteam Rogue ROM.")
	noesis.setToolFlags(handle, noesis.NTOOLFLAG_CONTEXTITEM)
	noesis.setToolVisibleCallback(handle, rogueDumpContextVisible)
	
	if len(TEST_DUMP_LIST) > 0:
		handle = noesis.registerTool("Fireteam Rogue (SNES) - Test Dump", rogueTestDumpToolMethod, "Dump a raw list of compressed chunks from TEST_DUMP_LIST.")
		noesis.setToolFlags(handle, noesis.NTOOLFLAG_CONTEXTITEM)
		noesis.setToolVisibleCallback(handle, rogueDumpContextVisible)
	
	return 1

def rogueValidateSfc(path):
	try:
		with open(path, "rb") as f:
			f.seek(0x7FC0, os.SEEK_SET) #assume headerless image, lorom
			id = f.read(14)
			if id == "FireTeam Rogue".encode("ASCII"):
				return True
	except:
		pass
	return False
	
def rogueDumpContextVisible(toolIndex, selectedFile):
	if not selectedFile:
		return 0
	nameNoExt, ext = os.path.splitext(selectedFile)
	ext = ext.lower()
	if ext != ".sfc":
		return 0
	if rogueValidateSfc(selectedFile):
		return 1
	return 0

def rogueReadTerminatedCompList(bs):
	offsets = []
	while not bs.checkEOF():
		addr = bs.readUInt24()
		if not addr:
			break
		offsets.append(snesLoRomPtrToFileOffset(addr))
	return offsets
	
def rogueRawDump(data, binName, suffix):
	name = os.path.splitext(binName)[0] + "." + suffix
	with open(name, "wb") as f:
		f.write(data)
	
def rogueDecompList(compList, data, mapData = None, lTable = None, applyLTable = None, applyDTable = None):
	if len(compList) == 0:
		return None
	d = bytearray()
	for compOffset in compList:
		d += rapi.callExtensionMethod("ftrogue_decomp", data[compOffset:], mapData, lTable)
	if applyLTable or applyDTable:
		rapi.callExtensionMethod("ftrogue_decomp_applytables", d, applyLTable, applyDTable, 0) #actual game typically uses 0x800 and increments from there due to palette placement
	return d

class BgEntry:
	def __init__(self, bs):
		self.width = bs.readUShort()
		self.height = bs.readUShort()
		self.palOffset = snesLoRomPtrToFileOffset(bs.readUInt24())
		self.c0 = rogueReadTerminatedCompList(bs)
		self.c1 = rogueReadTerminatedCompList(bs)
		self.c2 = rogueReadTerminatedCompList(bs)
		self.c3 = rogueReadTerminatedCompList(bs)
		self.c4 = rogueReadTerminatedCompList(bs)
		self.c5 = rogueReadTerminatedCompList(bs)
		
class FrameEntry:
	def __init__(self, bs):
		baseOffset = bs.tell()
		self.blockCount = bs.readUByte()
		dataOffset = baseOffset + bs.readUByte() + 1
		infoOffset = baseOffset + bs.readUByte() + 1
		
		bs.seek(baseOffset + 23, NOESEEK_ABS)
		self.basePosition = (bs.readUByte(), bs.readUByte())
		self.positions = [(bs.readUByte(), bs.readUByte()) for i in range(0, self.blockCount)]
		bs.seek(infoOffset, NOESEEK_ABS)
		#the game uses each value as an offset into a jump table, in order to jump to the appropriate routine to kick (potentially multiple) dma transfers.
		#we just convert it to a bit mask to specify tile layout.
		self.blockInfos = [15 - int((v & 31) >> 1) + (v & 0xE0) for v in bs.readBytes(self.blockCount)]
		dataSize = 0
		for info in self.blockInfos:
			setCount = (info & 1) + ((info >> 1) & 1) + ((info >> 2) & 1) + ((info >> 3) & 1)
			dataSize += 32 * setCount
		bs.seek(dataOffset, NOESEEK_ABS)
		self.data = bs.readBytes(dataSize)
		
		self.minX = self.maxX = self.positions[0][0]
		self.minY = self.maxY = self.positions[0][1]
		for blockIndex in range(0, self.blockCount):
			pos = self.positions[blockIndex]
			info = self.blockInfos[blockIndex]
			blockWidth = 16 if info & 10 else 8
			blockHeight = 16 if info & 12 else 8
			self.minX = min(self.minX, pos[0])
			self.minY = min(self.minY, pos[1])
			self.maxX = max(self.maxX, pos[0] + blockWidth)
			self.maxY = max(self.maxY, pos[1] + blockHeight)

def rogueParseOffsetTable(bs, tableAddr):
	bs.seek(snesLoRomPtrToFileOffset(tableAddr), NOESEEK_ABS)
	offsets = []
	while not bs.checkEOF():
		addr = bs.readUInt24()
		if addr >= 0xFF0000:
			break
		offsets.append(snesLoRomPtrToFileOffset(addr))
	return offsets
		
def rogueBgDump(binName, binData):
	bs = NoeBitStream(binData)

	bgOffsets = rogueParseOffsetTable(bs, BG_TABLE_ADDRESS)
		
	print("Found", len(bgOffsets), "background offsets.")
	for bgIndex in range(0, len(bgOffsets)):
		bs.seek(bgOffsets[bgIndex], NOESEEK_ABS)
		bg = BgEntry(bs)
		
		bs.seek(bg.palOffset, NOESEEK_ABS)
		palData = bs.readBytes(512)
		
		lTable = bytearray(0x20000)
		charData = rogueDecompList(bg.c0, binData, None, lTable)
		dTable = rogueDecompList(bg.c2, binData)
		mapData = rogueDecompList(bg.c1, binData, None, None, lTable, dTable)			
		mapLutData = rogueDecompList(bg.c3, binData, mapData, bytearray())
		colData = rogueDecompList(bg.c4, binData)
		colIdxData = rogueDecompList(bg.c5, binData, None, bytearray())

		if DUMP_RAW_BINARIES:
			rogueRawDump(charData, binName, "bg%03i.chardata.bin"%bgIndex)
			rogueRawDump(mapData, binName, "bg%03i.mapdata.bin"%bgIndex)
			rogueRawDump(mapLutData, binName, "bg%03i.maplutdata.bin"%bgIndex)
			rogueRawDump(colData, binName, "bg%03i.coldata.bin"%bgIndex)
			#the game converts the indices to word offsets into collision data on load, but we just leave it as-is
			rogueRawDump(colIdxData, binName, "bg%03i.colidxdata.bin"%bgIndex)

		drawFlags = 2

		blockWidth = bg.width
		blockHeight = bg.height
		tileWidth = blockWidth * 4
		tileHeight = blockHeight * 4
		texWidth = tileWidth * 8
		texHeight = tileHeight * 8
		
		mapBs = NoeBitStream(mapData)
		mapLutBs = NoeBitStream(mapLutData)
		mapLutBs.seek(len(mapLutData) - 4)
		extraTileSize = mapLutBs.readInt()
		mapLutBs.seek(len(mapLutData) - extraTileSize - blockWidth * blockHeight * 2)
		extraTileBs = NoeBitStream(mapLutData[len(mapLutData) - extraTileSize:])
		
		rgba = bytearray(texWidth * texHeight * 4)
		for blockY in range(0, blockHeight):
			tileY = blockY * 4
			for blockX in range(0, blockWidth):
				tileX = blockX * 4
				blockOffset = mapLutBs.readUShort()
				if blockOffset & 0x8000:
					extraTileBs.seek(blockOffset & 0x7FFF, NOESEEK_ABS)
					useBs = extraTileBs
				else:
					mapBs.seek(blockOffset, NOESEEK_ABS)
					useBs = mapBs

				for subTileY in range(0, 4):
					pixelY = (tileY + subTileY) * 8
					for subTileX in range(0, 4):
						pixelX = (tileX + subTileX) * 8
						tileData = useBs.readUShort()
						rapi.callExtensionMethod("snes_m1b0_drawtile_rgba", rgba, texWidth, texHeight, pixelX, pixelY, tileData, charData, palData, drawFlags)

		name = os.path.splitext(binName)[0] + ".bg%03i.png"%bgIndex
		print("Writing", name)
		noesis.saveImageRGBA(name, NoeTexture(name, texWidth, texHeight, rgba, noesis.NOESISTEX_RGBA32))
		
		if DRAW_COLLISION:
			rgba = bytearray(texWidth * texHeight * 4)
			rapi.callExtensionMethod("ftrogue_drawcol", rgba, binData, colData, colIdxData, blockWidth, blockHeight, snesLoRomPtrToFileOffset(COLLISION_LUT_ADDRESS), snesLoRomPtrToFileOffset(COLLISION_TILES_ADDRESS), 0)
			name = os.path.splitext(binName)[0] + ".bg%03i.col.png"%bgIndex
			print("Writing", name)
			noesis.saveImageRGBA(name, NoeTexture(name, texWidth, texHeight, rgba, noesis.NOESISTEX_RGBA32))

	return 0
	
def rogueFrameDump(binName, binData):
	bs = NoeBitStream(binData)

	palOffsets = rogueParseOffsetTable(bs, PALETTE_TABLE_ADDRESS)
	frameOffsets = rogueParseOffsetTable(bs, FRAME_TABLE_ADDRESS)
		
	print("Found", len(palOffsets), "palette offsets and", len(frameOffsets), "frame offsets.")
	if len(palOffsets) == 0 or len(frameOffsets) == 0:
		return 0

	#objects only reference frames via hardcoded tables which are interleaved with state machine code, and state machine functions are usually determined at runtime by
	#executing an initial state function. state functions are also prone to modifying the state function pointer by calling a function, grabbing the return address
	#right off the stack, and stuffing that into the state object's function pointer. this all means that we don't have a nice data-driven way to associate a given
	#frame with an object type, and as such we don't have a nice data-driven way to associate a frame with a palette. so, the user gets to just pick one! if you want
	#to take the time, you can define a map between the frame table and the palette table, but i can't be bothered to do this myself.
	palIndex = noesis.userPrompt(noesis.NOEUSERVAL_INT, "Select Palette", "Enter a palette index to use for this frame dump.", "33", None)
	if palIndex is None:
		return 0
		
	if palIndex < 0 or palIndex >= len(palOffsets):
		print("Warning: Palette index is out of range. Defaulting to 0.")
		palIndex = 0

	palOffset = palOffsets[palIndex]
	print("Reading palette at", palOffset)
	bs.seek(palOffset, NOESEEK_ABS)
	palData = bs.readBytes(512)

	drawFlags = 2
	tileOffsets = ((0, 0), (8, 0), (0, 8), (8, 8))

	allTextures = []
	
	for frameIndex in range(0, len(frameOffsets)):
		bs.seek(frameOffsets[frameIndex], NOESEEK_ABS)
		frame = FrameEntry(bs)
		
		if FIXED_CANVAS_SIZE:
			width, height = FIXED_CANVAS_SIZE
		else:
			width = frame.maxX - frame.minX
			height = frame.maxY - frame.minY
		if width <= 0 or height <= 0:
			print("Warning: Frame", frameIndex, "has bad dimensions:", frame.minX, frame.maxX, frame.minY, frame.maxY)
		else:
			rgba = bytearray(width * height * 4)
			dataOffset = 0
			for blockIndex in range(0, frame.blockCount):
				pos = frame.positions[blockIndex]
				info = frame.blockInfos[blockIndex]
				posX, posY = pos
				if not FIXED_CANVAS_SIZE:
					posX -= frame.minX
					posY -= frame.minY
				for tileIndex in range(0, 4):
					if info & (1 << tileIndex):
						tileOffset = tileOffsets[tileIndex]
						drawX = posX + tileOffset[0]
						drawY = posY + tileOffset[1]
						tileData = 0
						rapi.callExtensionMethod("snes_m1b0_drawtile_rgba", rgba, width, height, drawX, drawY, tileData, frame.data[dataOffset : dataOffset + 32], palData, drawFlags)
						dataOffset += 32

			name = os.path.splitext(binName)[0] + ".frame%03i.png"%frameIndex
			tex = NoeTexture(name, width, height, rgba, noesis.NOESISTEX_RGBA32)

			if USE_SINGLE_FILE:
				allTextures.append(tex)
			else:
				print("Writing", name)
				noesis.saveImageRGBA(name, tex)

	if len(allTextures) > 0:
		name = os.path.splitext(binName)[0] + ".allframes.gif"
		print("Writing", name)
		noesis.saveImageRGBA(name, allTextures)

	return 0
	
def rogueTestDump(binName, binData):
	for addr in TEST_DUMP_LIST:
		offset = snesLoRomPtrToFileOffset(addr)
		decompData = rapi.callExtensionMethod("ftrogue_decomp", binData[offset:], None, None)
		if decompData:
			name = os.path.splitext(binName)[0] + ".dump_%08x.bin"%addr
			print("Writing", name)
			with open(name, "wb") as f:
				f.write(decompData)
	return 0

def rogueGenericToolMethod(binProcess):
	noesis.logPopup()

	binName = noesis.getSelectedFile()
	if not binName or not os.path.exists(binName):
		noesis.messagePrompt("Selected file isn't readable through the standard filesystem.")
		return 0

	noeMod = noesis.instantiateModule()
	noesis.setModuleRAPI(noeMod)
	
	with open(binName, "rb") as f:
		binData = f.read()
	
	binProcess(binName, binData)

	noesis.freeModule(noeMod)
					
	return 0

def rogueBgDumpToolMethod(toolIndex):
	return rogueGenericToolMethod(rogueBgDump)

def rogueFrameDumpToolMethod(toolIndex):
	return rogueGenericToolMethod(rogueFrameDump)
	
def rogueTestDumpToolMethod(toolIndex):
	return rogueGenericToolMethod(rogueTestDump)
