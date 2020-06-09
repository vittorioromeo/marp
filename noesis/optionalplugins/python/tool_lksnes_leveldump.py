from inc_noesis import *
from inc_romcom import snesHiRomPtrToFileOffset
import os

#parse this many levels, assuming playlist pointer doesn't follow level structure order
LEVEL_COUNT = 16

LOAD_OBJECTS = False

def registerNoesisTypes():
	handle = noesis.registerTool("Lion King (SNES) - Level Dump", lkDumpToolMethod, "Dump levels from Lion King ROM.")
	noesis.setToolFlags(handle, noesis.NTOOLFLAG_CONTEXTITEM)
	noesis.setToolVisibleCallback(handle, lkDumpContextVisible)
	
	return 1

def lkValidateSfc(path):
	try:
		with open(path, "rb") as f:
			f.seek(0xffc0, os.SEEK_SET) #assume headerless image
			id = f.read(9)
			if id == "LION KING".encode("ASCII"):
				return True
	except:
		pass
	return False
	
def lkDumpContextVisible(toolIndex, selectedFile):
	if not selectedFile:
		return 0
	nameNoExt, ext = os.path.splitext(selectedFile)
	ext = ext.lower()
	if ext != ".sfc":
		return 0
	if lkValidateSfc(selectedFile):
		return 1
	return 0
		
def decompLkLz(addr, romData):
	if addr == 0:
		return None
	return rapi.callExtensionMethod("lklz_decomp", romData[addr:])

def snesPtr(data):
	return data[0] | (data[1] << 8) | (data[2] << 16)
	
def countContiguousLevelPointers(data, offset):
	levelCount = 1
	curPtr = snesPtr(data[offset:offset + 3])
	offset += 3
	while True:
		nextPtr = snesPtr(data[offset:offset + 3])
		if nextPtr != curPtr + 50:
			break
		curPtr = nextPtr
		levelCount += 1
		offset += 3
	return levelCount

class LevelEntry:
	def __init__(self, data):
		bs = NoeBitStream(data)
		self.floorAddr = snesHiRomPtrToFileOffset(bs.readUInt24())
		self.p1 = bs.readUInt24()
		self.tileAddr = snesHiRomPtrToFileOffset(bs.readUInt24())
		self.mapAddr = snesHiRomPtrToFileOffset(bs.readUInt24())
		self.palAddr = snesHiRomPtrToFileOffset(bs.readUInt24())
		self.blockAddr = snesHiRomPtrToFileOffset(bs.readUInt24())
		#width/height are in tiles
		self.width = bs.readUShort()
		self.height = bs.readUShort() * 2
		self.u0 = bs.readUShort()
		self.u1 = bs.readUShort()
		self.paraAddr = snesHiRomPtrToFileOffset(bs.readUInt24())
		self.u2 = bs.readUShort()
		self.u3 = bs.readUShort()
		self.u4 = bs.readUShort()
		self.u5 = bs.readUShort()
		self.p4 = bs.readUInt24()
		self.p5 = bs.readUInt24()
		self.u6 = bs.readUShort()
		self.u7 = bs.readUShort()
		self.u8 = bs.readUShort()
		
	def validate(self, data):
		return self.tileAddr >= 0 and self.tileAddr < len(data) and self.palAddr >= 0 and self.palAddr < len(data)

def lkDumpToolMethod(toolIndex):
	noesis.logPopup()

	binName = noesis.getSelectedFile()
	if not binName or not os.path.exists(binName):
		noesis.messagePrompt("Selected file isn't readable through the standard filesystem.")
		return 0
		
	noeMod = noesis.instantiateModule()
	noesis.setModuleRAPI(noeMod)
	
	with open(binName, "rb") as f:
		data = f.read()
		#search the first 4KB for level pointer list
		levelPtrOffset = -1
		for offset in range(0, 0x1000):
			addr = snesPtr(data[offset:offset + 3])
			#expect structures to live in the first bank
			if addr >= 0xC00000 and addr < 0xC10000:
				levelCount = countContiguousLevelPointers(data, offset)
				if levelCount >= 6: #require a minimum of 6
					levelPtrOffset = offset
					break

		if levelPtrOffset >= 0:
			drawFlags = 2
			
			print("Found", levelCount, "contiguous level pointers at offset", levelPtrOffset, "- parsing", LEVEL_COUNT, "levels from list.")
			for levelIndex in range(0, LEVEL_COUNT):
				ptrOffset = levelPtrOffset + levelIndex * 3
				levelAddr = snesPtr(data[ptrOffset : ptrOffset + 3])
				levelOffset = snesHiRomPtrToFileOffset(levelAddr)

				levelEntry = LevelEntry(data[levelOffset : levelOffset + 50])
				if not levelEntry.validate(data):
					break
					
				if levelEntry.tileAddr and levelEntry.palAddr:
					charData = decompLkLz(levelEntry.tileAddr, data)
					palData = data[levelEntry.palAddr : levelEntry.palAddr + 512]
					
					if levelEntry.mapAddr and levelEntry.blockAddr:
						mapData = decompLkLz(levelEntry.mapAddr, data)
						texWidth = levelEntry.width * 8
						texHeight = levelEntry.height * 8
						rgba = bytearray(texWidth * texHeight * 4)
						bs = NoeBitStream(mapData)
						for blockY in range(0, levelEntry.height // 2):
							pixelY = blockY * 16
							for blockX in range(0, levelEntry.width // 2):
								pixelX = blockX * 16
								blockAddr = levelEntry.blockAddr + bs.readUShort()
								tileUL, tileUR, tileLL, tileLR = noeUnpack("<HHHH", data[blockAddr : blockAddr + 8])
								rapi.callExtensionMethod("snes_m1b0_drawtile_rgba", rgba, texWidth, texHeight, pixelX, pixelY, tileUL, charData, palData, drawFlags)
								rapi.callExtensionMethod("snes_m1b0_drawtile_rgba", rgba, texWidth, texHeight, pixelX + 8, pixelY, tileUR, charData, palData, drawFlags)
								rapi.callExtensionMethod("snes_m1b0_drawtile_rgba", rgba, texWidth, texHeight, pixelX, pixelY + 8, tileLL, charData, palData, drawFlags)
								rapi.callExtensionMethod("snes_m1b0_drawtile_rgba", rgba, texWidth, texHeight, pixelX + 8, pixelY + 8, tileLR, charData, palData, drawFlags)
								
						if LOAD_OBJECTS and levelEntry.floorAddr:
							floorData = decompLkLz(levelEntry.floorAddr, data)
							bs = NoeBitStream(mapData)
							for blockY in range(0, levelEntry.height // 2):
								pixelY = blockY * 16
								for blockX in range(0, levelEntry.width // 2):
									pixelX = blockX * 16
									floorAddr = bs.readUShort() >> 1
									a0, a1, a2, a3 = noeUnpack("BBBB", floorData[floorAddr : floorAddr + 4])
									if a3 != 0:
										objectIdString = "%i"%a3
										#draw a shadow first
										rapi.callExtensionMethod("drawtext_8x8_rgba", rgba, texWidth, texHeight, pixelX + 8, pixelY + 4, 3, (0, 0, 0, 100), objectIdString)
										#then the text
										rapi.callExtensionMethod("drawtext_8x8_rgba", rgba, texWidth, texHeight, pixelX + 8, pixelY + 4, 1, (127, 255, 0), objectIdString)										
								
						name = os.path.splitext(binName)[0] + ".level%02i.bg.png"%levelIndex
						print("Writing", name)
						noesis.saveImageRGBA(name, NoeTexture(name, texWidth, texHeight, rgba, noesis.NOESISTEX_RGBA32))				
					
					if levelEntry.paraAddr:
						paraMapData = decompLkLz(levelEntry.paraAddr, data)
						paraWidth = 64 if levelIndex != 3 else 32 #stampede hack
						paraHeight = len(paraMapData) // (paraWidth * 2)
						paraTexWidth = paraWidth * 8
						paraTexHeight = paraHeight * 8
						rgba = bytearray(paraTexWidth * paraTexHeight * 4)
						bs = NoeBitStream(paraMapData)
						for tileY in range(0, paraHeight):
							pixelY = tileY * 8
							for tileX in range(0, paraWidth):
								pixelX = tileX * 8
								tileData = bs.readUShort()
								rapi.callExtensionMethod("snes_m1b0_drawtile_rgba", rgba, paraTexWidth, paraTexHeight, pixelX, pixelY, tileData, charData, palData, drawFlags)
								
						name = os.path.splitext(binName)[0] + ".level%02i.para.png"%levelIndex
						print("Writing", name)
						noesis.saveImageRGBA(name, NoeTexture(name, paraTexWidth, paraTexHeight, rgba, noesis.NOESISTEX_RGBA32))

		else:
			print("Failed to find level pointer memory.")

		
	noesis.freeModule(noeMod)

	return 0
	