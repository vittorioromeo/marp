from inc_noesis import *
import os

LOAD_OBJECTS = False
CHECK_USED_OBJECTS = False #some levels still have stale objects for previously-used id's, this will tell us which ones are really never placed in any of the levels.
DUMP_PALETTES = False

def registerNoesisTypes():
	handle = noesis.registerTool("Aladdin (Genesis) - Level Dump", alDumpToolMethod, "Dump levels from Aladdin ROM.")
	noesis.setToolFlags(handle, noesis.NTOOLFLAG_CONTEXTITEM)
	noesis.setToolVisibleCallback(handle, alDumpContextVisible)
	
	return 1

def alValidateRom(path):
	try:
		with open(path, "rb") as f:
			f.seek(0x100, os.SEEK_SET) #assume headerless image
			segaId = f.read(4)
			if segaId == "SEGA".encode("ASCII"): #don't care about region or version, since we check for data that exists in all known distributions
				f.seek(0x120, os.SEEK_SET)
				gameId = f.read(7)
				if gameId == "ALADDIN".encode("ASCII") or gameId == "THE JUN".encode("ASCII"): #second bit is a silly hack to allow this to be used on the CES demo
					return True
	except:
		pass
	return False

def alDumpContextVisible(toolIndex, selectedFile):
	if not selectedFile:
		return 0
	nameNoExt, ext = os.path.splitext(selectedFile)
	ext = ext.lower()
	if ext != ".bin" and ext != ".md":
		return 0
	if alValidateRom(selectedFile):
		return 1
	return 0
	
class LevelEntry:
	def __init__(self, data):
		bs = NoeBitStream(data, NOE_BIGENDIAN)
		self.startX = bs.readUShort()
		self.startY = bs.readUShort()
		self.ofsX = bs.readUShort()
		self.ofsY = bs.readUShort()
		self.floorAddr = bs.readUInt()
		self.charsAddr = bs.readUInt()
		self.mapAddr = bs.readUInt()
		self.animAddr = bs.readUInt()
		self.animSize = bs.readUShort()
		self.musicId = bs.readUShort()
		self.paraAddr = bs.readUInt()
		self.palAddr = bs.readUInt()
		self.blockAddr = bs.readUInt()
		self.exitFnAddr = bs.readUInt()
		self.enterFnAddr = bs.readUInt()
		self.blockWidth = bs.readUShort()
		self.blockHeight = bs.readUShort()
		self.paraFnAddr = bs.readUInt()
		bs.readUInt() #unused
		bs.readUInt() #unused
		self.bgSwap = bs.readByte()
		self.pad = bs.readByte()
		
	def validateCompressionAddr(self, addr, romData, allowZero):
		if addr < 0 or addr > len(romData) - 18:
			self.isValid = False
		elif addr == 0:
			if not allowZero:
				self.isValid = False
		else:
			id = noeUnpack("<I", romData[addr : addr + 4])[0]
			if id != 0x1434E52: #always expect PP mode 1
				self.isValid = False
			
	def validate(self, romData):
		self.isValid = True
		if self.pad != 0:
			self.isValid = False
		self.validateCompressionAddr(self.floorAddr, romData, False)
		self.validateCompressionAddr(self.charsAddr, romData, False)
		self.validateCompressionAddr(self.mapAddr, romData, False)
		self.validateCompressionAddr(self.paraAddr, romData, True)
		return self.isValid
		
def decompRNC(addr, romData):
	if addr == 0:
		return None
	decompSize, compSize = noeUnpack(">II", romData[addr + 4 : addr + 12])
	if decompSize == 0: #carved out entry
		return None
	return rapi.decompRNC(romData[addr : addr + compSize + 18], decompSize)
		
def dumpPalScratch(data, path, colorCount):
	with open(path, "w") as fw:
		fw.write("JASC-PAL\n0100\n%i\n"%(colorCount))
		for palIndex in range(0, colorCount):
			r = data[palIndex * 4 + 0]
			g = data[palIndex * 4 + 1]
			b = data[palIndex * 4 + 2]
			fw.write("%i %i %i\n"%(r, g, b))
	return 0
		
def alDumpToolMethod(toolIndex):
	noesis.logPopup()

	binName = noesis.getSelectedFile()
	if not binName or not os.path.exists(binName):
		noesis.messagePrompt("Selected file isn't readable through the standard filesystem.")
		return 0

	#expect level data after dampening (y) table
	findValues = (0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 3, 4, 4, 4, 4, 4, 5, 5, 5, 5, 5, 6, 6, 6, 6, 6, 7, 7, 7, 7, 7, 7, 8, 8, 8, 8, 8, 8, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 13, 13, 13, 13, 13, 13, 13, 13, 13, 13, 13, 13, 13, 13, 13, 13, 13, 13, 13, 13, 13, 13, 13, 13, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15)
	findData = noePack("B" * len(findValues), *findValues)

	noeMod = noesis.instantiateModule()
	noesis.setModuleRAPI(noeMod)
	
	with open(binName, "rb") as f:
		data = f.read()
		offset = data.find(findData)
		if offset <= 0:
			print("Failed to find marker data in binary.")
		else:
			offset += len(findData)
			offset = (offset + 1) & ~1
			levelCount = 0
			startOffset = offset

			if CHECK_USED_OBJECTS:
				usedObjects = set()
				
			while offset < len(data):
				levelEntry = LevelEntry(data[offset : offset + 66])
				if not levelEntry.validate(data):
					break
					
				if levelCount != 8: #too much special-casing for 8
					charData = decompRNC(levelEntry.charsAddr, data)
					if charData: #allow for this to be emptied out for patched roms
						mapData = decompRNC(levelEntry.mapAddr, data)
						paraData = decompRNC(levelEntry.paraAddr, data)
						palSize = 16 * 2 * 4
						palData = data[levelEntry.palAddr : levelEntry.palAddr + palSize]
						if LOAD_OBJECTS:
							floorData = decompRNC(levelEntry.floorAddr, data)

						print("Processing level", levelCount, "-", levelEntry.blockWidth, "*", levelEntry.blockHeight, "-", offset, "-", len(charData), "-", len(mapData), "-", len(paraData) if paraData else 0)
						
						colorRampIndex = 6

						if DUMP_PALETTES:
							scratchFlags = colorRampIndex << 24
							palScratch = bytearray(8 * 8 * 4)
							charScratch = bytearray(((0 << 4) | 1, (2 << 4) | 3, (4 << 4) | 5, (6 << 4) | 7, (8 << 4) | 9, (10 << 4) | 11, (12 << 4) | 13, (14 << 4) | 15) * 4)
							rapi.callExtensionMethod("vdp_drawtile_rgba", palScratch, 8, 8, 0, 0, 0x00, charScratch, palData, scratchFlags)
							dumpPalScratch(palScratch, os.path.splitext(binName)[0] + ".level%02i.pal0.pal"%levelCount, 16)
							rapi.callExtensionMethod("vdp_drawtile_rgba", palScratch, 8, 8, 0, 0, 0x20, charScratch, palData, scratchFlags)
							dumpPalScratch(palScratch, os.path.splitext(binName)[0] + ".level%02i.pal1.pal"%levelCount, 16)
							rapi.callExtensionMethod("vdp_drawtile_rgba", palScratch, 8, 8, 0, 0, 0x40, charScratch, palData, scratchFlags)
							dumpPalScratch(palScratch, os.path.splitext(binName)[0] + ".level%02i.pal2.pal"%levelCount, 16)
							rapi.callExtensionMethod("vdp_drawtile_rgba", palScratch, 8, 8, 0, 0, 0x60, charScratch, palData, scratchFlags)
							dumpPalScratch(palScratch, os.path.splitext(binName)[0] + ".level%02i.pal3.pal"%levelCount, 16)

						drawFlags = 2 | (colorRampIndex << 24)
							
						#do background
						tileWidth = levelEntry.blockWidth << 1
						tileHeight = levelEntry.blockHeight << 1
						texWidth = tileWidth << 3
						texHeight = tileHeight << 3
						
						rgba = bytearray(texWidth * texHeight * 4)
						mapBs = NoeBitStream(mapData, NOE_BIGENDIAN)
						for blockY in range(0, levelEntry.blockHeight):
							pixelY = blockY << 4
							for blockX in range(0, levelEntry.blockWidth):
								pixelX = blockX << 4
								blockOffset = mapBs.readUShort()
								blockAddr = levelEntry.blockAddr + blockOffset								
								#intentionally unpack as LE, let vdp renderer deal with native endian
								tileUL, tileUR, tileLL, tileLR = noeUnpack("<HHHH", data[blockAddr : blockAddr + 8])
								rapi.callExtensionMethod("vdp_drawtile_rgba", rgba, texWidth, texHeight, pixelX, pixelY, tileUL, charData, palData, drawFlags)
								rapi.callExtensionMethod("vdp_drawtile_rgba", rgba, texWidth, texHeight, pixelX + 8, pixelY, tileUR, charData, palData, drawFlags)
								rapi.callExtensionMethod("vdp_drawtile_rgba", rgba, texWidth, texHeight, pixelX, pixelY + 8, tileLL, charData, palData, drawFlags)
								rapi.callExtensionMethod("vdp_drawtile_rgba", rgba, texWidth, texHeight, pixelX + 8, pixelY + 8, tileLR, charData, palData, drawFlags)
						
						if LOAD_OBJECTS:
							mapBs.seek(0, NOESEEK_ABS)
							for blockY in range(0, levelEntry.blockHeight):
								pixelY = blockY << 4
								for blockX in range(0, levelEntry.blockWidth):
									pixelX = blockX << 4
									blockOffset = mapBs.readUShort()
									floorOffset = blockOffset >> 1
									objectTile = floorData[floorOffset + 3]
									"""
									c0 = floorData[floorOffset]
									c1 = floorData[floorOffset + 1]
									specialTile = floorData[floorOffset + 2]
									if c0 != 0:
										conIdString = "%i"%c0
										rapi.callExtensionMethod("drawtext_8x8_rgba", rgba, texWidth, texHeight, pixelX + 8, pixelY + 4, 3, (0, 0, 0, 100), conIdString)
										rapi.callExtensionMethod("drawtext_8x8_rgba", rgba, texWidth, texHeight, pixelX + 8, pixelY + 4, 1, (0, 255, 255), conIdString)
									if specialTile != 0:
										specialIdString = "%i"%specialTile
										rapi.callExtensionMethod("drawtext_8x8_rgba", rgba, texWidth, texHeight, pixelX + 8, pixelY + 4, 3, (0, 0, 0, 100), specialIdString)
										rapi.callExtensionMethod("drawtext_8x8_rgba", rgba, texWidth, texHeight, pixelX + 8, pixelY + 4, 1, (255, 0, 0), specialIdString)
									"""
									if objectTile != 0:
										if CHECK_USED_OBJECTS:
											usedObjects.add(objectTile)
										objectIdString = "%i"%objectTile
										#draw a shadow first
										rapi.callExtensionMethod("drawtext_8x8_rgba", rgba, texWidth, texHeight, pixelX + 8, pixelY + 4, 3, (0, 0, 0, 100), objectIdString)
										#then the text
										rapi.callExtensionMethod("drawtext_8x8_rgba", rgba, texWidth, texHeight, pixelX + 8, pixelY + 4, 1, (127, 255, 0), objectIdString)
						
						name = os.path.splitext(binName)[0] + ".level%02i.bg.png"%levelCount
						print("Writing", name)
						noesis.saveImageRGBA(name, NoeTexture(name, texWidth, texHeight, rgba, noesis.NOESISTEX_RGBA32))

						#do parallax
						if paraData:
							tileWidth = 64
							tileHeight = len(paraData) // (tileWidth * 2)
							texWidth = tileWidth << 3
							texHeight = tileHeight << 3
							
							rgba = bytearray(texWidth * texHeight * 4)				
							paraBs = NoeBitStream(paraData, NOE_LITTLEENDIAN)				
							for tileY in range(0, tileHeight):
								pixelY = tileY << 3
								for tileX in range(0, tileWidth):
									pixelX = tileX << 3
									tileData = paraBs.readUShort()
									rapi.callExtensionMethod("vdp_drawtile_rgba", rgba, texWidth, texHeight, pixelX, pixelY, tileData, charData, palData, drawFlags)

							name = os.path.splitext(binName)[0] + ".level%02i.para.png"%levelCount
							print("Writing", name)
							noesis.saveImageRGBA(name, NoeTexture(name, texWidth, texHeight, rgba, noesis.NOESISTEX_RGBA32))
								
				offset += 66
				levelCount += 1
				
			print("Parsed", levelCount, "levels from table at", startOffset)
		
			if CHECK_USED_OBJECTS:
				for objectIndex in range(0, 256):
					if objectIndex not in usedObjects:
						print("Unused:", objectIndex)
		
	noesis.freeModule(noeMod)

	return 0
	