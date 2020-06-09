#Noesis Famicom Disk System support
#written with https://wiki.nesdev.com/w/index.php/FDS_disk_format as reference
from inc_noesis import *
import os

FDS_SIDE_SIZE = 65500

def registerNoesisTypes():
	handle = noesis.register("FDS container", ".fds")
	noesis.setHandlerExtractArc(handle, fdsExtractArc)
	return 1

class FdsFileInfo:
	def __init__(self, bs):
		self.num = bs.readUByte()
		self.id = bs.readUByte()
		self.name = noeStrFromBytes(bs.readBytes(8))
		self.destAddr = bs.readUShort()
		self.size = bs.readUShort()
		self.type = bs.readUByte()
	def getExt(self):
		knownTypes = { 0 : "PRAM", 1: "CRAM", 2 : "VRAM" }
		if self.type not in knownTypes:
			return ".BIN"
		return "." + knownTypes[self.type]
	
def fdsExtractArc(fileName, fileLen, justChecking):
	if fileLen <= 32:
		return 0

	with open(fileName, "rb") as f:
		id, sideCount = noeUnpack("<IB", f.read(5))
		sideOffset = 16
		if id != 0x1A534446 or sideCount == 0:
			#in this case, we might just be missing the fds header (but still assume no crcs/gaps)
			sideOffset = 0
			sideCount = fileLen // FDS_SIDE_SIZE
		expectedSize = sideOffset + sideCount * FDS_SIDE_SIZE
		if expectedSize > fileLen:
			return 0
		#only bother verifying the first side
		f.seek(sideOffset, os.SEEK_SET)
		id = f.read(15)
		if id[0] != 1 or id[1:] != "*NINTENDO-HVC*".encode("ASCII"):
			return 0
		if justChecking:
			return 1

		for sideIndex in range(0, sideCount):
			f.seek(sideOffset + sideIndex * FDS_SIDE_SIZE, os.SEEK_SET)
			bs = NoeBitStream(f.read(FDS_SIDE_SIZE))
			currentFileInfo = None
			while not bs.checkEOF():
				blockType = bs.readUByte()
				if blockType == 1:
					#info block, don't care about anything in here for our purposes
					bs.seek(0x37, NOESEEK_REL)
				elif blockType == 2:
					#file count, also don't care because we'll still read any files beyond this count
					bs.seek(0x01, NOESEEK_REL)
				elif blockType == 3:
					currentFileInfo = FdsFileInfo(bs)
				elif blockType == 4:
					if not currentFileInfo:
						print("Error: Encountered data block without file info at", sideIndex, "-", bs.tell())
						break
					else:
						data = bs.readBytes(currentFileInfo.size)
						exPath = "side%02i/"%sideIndex + currentFileInfo.name + currentFileInfo.getExt()
						print("Writing", exPath, "-", "num:", currentFileInfo.num, "id:", currentFileInfo.id, "dest: %04X"%currentFileInfo.destAddr)
						rapi.exportArchiveFile(exPath, data)
						currentFileInfo = None
				elif blockType != 0:
					print("Error: Unknown block type", blockType, "at", sideIndex, "-", bs.tell())
					break

	return 1
