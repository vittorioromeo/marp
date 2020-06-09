from inc_noesis import *

def registerNoesisTypes():
	handle = noesis.register("PKM Image", ".pkm")
	noesis.setHandlerTypeCheck(handle, pkmCheckType)
	noesis.setHandlerLoadRGBA(handle, pkmLoadRGBA)
	return 1
	
class PKMImage:
	def __init__(self, reader):
		self.reader = reader

	def parseImageInfo(self):
		bs = self.reader
		if bs.getSize() < 16:
			return -1
		bs.seek(0, NOESEEK_ABS)
		magic = bs.readUInt()
		if magic != 0x504B4D20:
			return -1
		ver = bs.readUShort()
		if ver != 0x3230 and ver != 0x3130:
			return -1
		self.format = bs.readUShort()
		formatToString = (
			"rgb1",
			"rgb",
			"rgba",
			"rgba",
			"rgba1",
			"r",
			"rg",
			"rs",
			"rgs",
			"srgb",
			"srgba",
			"srgba1"
		)
		if self.format < 0 or self.format >= len(formatToString):
			return -1
		self.formatString = formatToString[self.format]
		self.alignedWidth = bs.readUShort()
		self.alignedHeight = bs.readUShort()
		self.width = bs.readUShort()
		self.height = bs.readUShort()
		self.dataOffset = bs.tell()
		return 0
		
	def decode(self):
		bs = self.reader
		remainingBuffer = bs.getBuffer()[self.dataOffset:]
		data = rapi.callExtensionMethod("etc_decoderaw32", remainingBuffer, self.width, self.height, self.formatString)
		return data
	
def pkmCheckType(data):
	pkm = PKMImage(NoeBitStream(data, NOE_BIGENDIAN))
	if pkm.parseImageInfo() != 0:
		return 0
	return 1

def pkmLoadRGBA(data, texList):
	pkm = PKMImage(NoeBitStream(data, NOE_BIGENDIAN))
	if pkm.parseImageInfo() != 0:
		return 0
	texList.append(NoeTexture("pkmtex", pkm.width, pkm.height, pkm.decode(), noesis.NOESISTEX_RGBA32))
	return 1
