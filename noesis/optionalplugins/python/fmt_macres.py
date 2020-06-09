#loads/dumps Mac resource files, written using:
# Inside Macintosh: More Macintosh Toolbox / Chapter 1 - Resource Manager / Resource Manager Reference

from inc_noesis import *
from inc_imgtools import macEsperantoToAscii, macTypeToString

MAC_PICT_ALLOW_OVERSCAN = 0

def registerNoesisTypes():
	handle = noesis.register("Mac Resource container", ".appl;.zsys")
	noesis.setHandlerExtractArc(handle, mcrExtractArc)
	
	#just for the hell of it
	handle = noesis.register("Mac Resource Icon", ".macres_icn#")
	noesis.setHandlerTypeCheck(handle, macIconCheckType)
	noesis.setHandlerLoadRGBA(handle, macIconLoadRGBA)
	
	#typically comes out of scrapbooks
	handle = noesis.register("Mac Resource PICT", ".macres_pict")
	noesis.setHandlerTypeCheck(handle, macPictCheckType)
	noesis.setHandlerLoadRGBA(handle, macPictLoadRGBA)
	
	return 1

class MacResFile:
	def __init__(self, fileSize):
		self.fileSize = fileSize

	def parseHeader(self, bs):
		self.resDataOffset = bs.readUInt()
		self.resMapOffset = bs.readUInt()
		self.resDataSize = bs.readUInt()
		self.resMapSize = bs.readUInt()
		
	def parseMap(self, bs):
		bs.seek(self.resMapOffset, NOESEEK_ABS)
		self.resMap = MacResMap(bs)

	def isValid(self):
		if self.resDataOffset < 16 or self.resMapOffset < 16:
			return False
		dataEnd = self.resDataOffset + self.resDataSize
		mapEnd = self.resMapOffset + self.resMapSize
		if dataEnd > self.fileSize or mapEnd > self.fileSize:
			return False
		return True
		
	def findType(self, type):
		for resType in self.resMap.typeList:
			if resType.type == type:
				return resType
		return None
		
	def findRef(self, type, id):
		resType = self.findType(type)
		if resType:
			for ref in resType.refList:
				if ref.id == id:
					return ref
		return None

	def readRefData(self, bs, type, id):
		ref = self.findRef(type, id)
		if ref:
			dataOffset = self.resDataOffset + ref.dataOffset
			bs.seek(dataOffset, NOESEEK_ABS)
			dataSize = bs.readUInt()
			return bs.readBytes(dataSize)
		return None			
		
class MacResMap:
	def __init__(self, bs):
		self.baseOffset = bs.tell()
		bs.seek(22, NOESEEK_REL)
		self.attrib = bs.readUShort()
		typeListOffset = self.baseOffset + bs.readUShort()
		namesOffset = self.baseOffset + bs.readUShort()
		
		bs.seek(typeListOffset, NOESEEK_ABS)
		typeCount = bs.readUShort() + 1
		self.typeList = [MacResType(bs) for x in range(0, typeCount)]
		for resType in self.typeList:
			resType.parseRefs(bs, typeListOffset, namesOffset)
		
class MacResType:
	def __init__(self, bs):
		self.type = bs.readUInt()
		self.refCount = bs.readUShort() + 1
		self.refListOffset = bs.readUShort()
	def parseRefs(self, bs, baseOffset, namesOffset):
		bs.seek(baseOffset + self.refListOffset, NOESEEK_ABS)
		self.refList = sorted([MacResTypeRef(bs) for x in range(0, self.refCount)], key=lambda a: a.id) #sort by id so we're grouped better by id in dump
		for ref in self.refList:
			if ref.nameOffset != 0xFFFF:
				bs.seek(namesOffset + ref.nameOffset)
				nameSize = bs.readUByte()
				if nameSize > 0:
					nameData = bs.readBytes(nameSize)
					firstZero = nameData.find(b"\0")
					if firstZero >= 0:
						nameData = nameData[:firstZero]
					ref.name = macEsperantoToAscii(nameData)

class MacResTypeRef:
	def __init__(self, bs):
		self.name = None
		self.id = bs.readUShort()
		self.nameOffset = bs.readUShort()
		self.attrib = bs.readUByte()
		self.dataOffset = bs.readUInt24()
		self.resv = bs.readUInt()

def mcrLoadFromFile(bs, fileSize, testingValidity):
	res = MacResFile(fileSize)
	res.parseHeader(bs)
	if not res.isValid():
		return None
		
	if testingValidity:
		return res
		
	res.parseMap(bs)

	return res

def mcrExtractArc(fileName, fileLen, justChecking):
	if fileLen <= 16:
		return 0

	with open(fileName, "rb") as f:	
		bs = NoeFileStream(f, NOE_BIGENDIAN)
		res = mcrLoadFromFile(bs, bs.fileSize, justChecking)
		if not res:
			return 0
		if justChecking:
			return 1
		
		fileCount = 0
		for resType in res.resMap.typeList:
			typeStr = macTypeToString(resType.type)
			typeExt = "macres_" + typeStr
			for ref in resType.refList:
				dataOffset = res.resDataOffset + ref.dataOffset
				bs.seek(dataOffset, NOESEEK_ABS)
				dataSize = bs.readUInt()
				if dataOffset + 4 + dataSize > fileLen:
					print("Warning: Encountered bad resource size at", dataOffset)
				else:
					data = bs.readBytes(dataSize)
					name = "res_" + typeStr + "_%04i"%fileCount + "_id%04x"%ref.id
					if ref.name:
						name += "_" + ref.name
					name += "." + typeExt
					print("Writing", name)
					rapi.exportArchiveFile(name, data)
				fileCount += 1

	return 1
	
def macIconCheckType(data):
	if len(data) < 256:
		return 0
	return 1
	
def macIconLoadRGBA(data, texList):
	width = 32
	height = 32
	colorBlack = bytearray((0, 0, 0, 255))
	colorWhite = bytearray((255, 255, 255, 255))

	rgba = bytearray()
	for y in range(0, height):
		for x in range(0, width // 8):
			c = data[y * 4 + x]
			m = data[128 + y * 4 + x]
			for i in range(0, 8):
				pixelColor = colorBlack if c & 0x80 else colorWhite
				pixelColor[3] = 255 if m & 0x80 else 0
				c <<= 1
				m <<= 1
				rgba += pixelColor

	texList.append(NoeTexture("macicon", width, height, rgba, noesis.NOESISTEX_RGBA32))
	return 1

class PictRect:
	def __init__(self, bs):
		self.top = bs.readUShort()
		self.left = bs.readUShort()
		self.bottom = bs.readUShort()
		self.right = bs.readUShort()
	def getWidth(self):
		return self.right - self.left
	def getHeight(self):
		return self.bottom - self.top
	
class MacPictFile:
	def __init__(self, data):
		self.versionOp = 0
		self.version = 0
		if len(data) >= 12:
			bs = NoeBitStream(data, NOE_BIGENDIAN)
			bs.setByteEndianForBits(NOE_BIGENDIAN)
			size = bs.readUShort()
			if size <= len(data):
				self.rect = PictRect(bs)
				self.versionOp = bs.readUByte()
				self.version = bs.readUByte()
				self.opOffset = bs.tell()
				self.bs = bs
			
	def isSupported(self):
		#only supporting v1 files, since this is all i have on-hand right now
		return self.versionOp == 0x11 and self.version == 0x01
	
def macPictCheckType(data):
	pict = MacPictFile(data)
	if not pict.isSupported():
		return 0
	return 1

#see http://web.archive.org/web/19990203033814/http://developer.apple.com/technotes/qd/qd_14.html
def macPictUnpackBits(op, pict, bs):
	hasRegion = op == 0x91 or op == 0x99
	isRaw = op == 0x90 or op == 0x91
	startOffset = bs.tell()
	rowBytes = bs.readUShort()
	bounds = PictRect(bs)
	srcRect = PictRect(bs)
	dstRect = PictRect(bs)
	mode = bs.readUShort()
	if hasRegion:
		maskRgnSize = bs.readUShort()
		bs.seek(maskRgnSize - 2, NOESEEK_REL)
	rawBlack = bytearray([0, 0, 0, 255])
	rawWhite = bytearray([255, 255, 255, 255])

	imgWidth = rowBytes * 8
	imgHeight = bounds.getHeight()
	rgba = bytearray()
	for rowIndex in range(0, imgHeight):
		if isRaw:
			bs.pushOffset()
			for rowOffset in range(0, rowBytes * 8):
				color = rawBlack if bs.readBits(1) else rawWhite
				rgba += color
			bs.popOffset()
			bs.seek(rowBytes, NOESEEK_REL)
		else:
			rowSize = bs.readUByte()
			if rowSize > 0:
				rgba += rapi.callExtensionMethod("macpaint_rle_decode", bs.readBytes(rowSize), rowBytes * 8, 1)
			else: #empty row - unsure if this is normally possible, but helps gracefully handle some corrupt data i've come across (which normally causes scrapbook to crash or lock up)
				rgba += rawWhite * rowBytes * 8

	srcX = srcRect.left - bounds.left
	srcY = srcRect.top - bounds.top
	srcWidth = srcRect.getWidth()
	srcHeight = srcRect.getHeight()

	#possible todo - support additional modes? none of my test data needs this	
	rapi.imageBlit32(pict.canvas, pict.canvasWidth, pict.canvasHeight, dstRect.left - pict.rect.left, dstRect.top - pict.rect.top, rgba, srcWidth, srcHeight, srcX, srcY, pict.canvasWidth * 4, imgWidth * 4)

	return bs.tell() - startOffset

def macPictLoadRGBA(data, texList):
	pict = MacPictFile(data)
	bs = pict.bs
	bs.seek(pict.opOffset, NOESEEK_ABS)

	#only intended to get far enough to rip out packbits data, will break when it encounters anything else.
	#this is also structured around the monochrome pict format used by scrapbook, rather than the form most modern tools support. (so sticking to the macres_pict extension is a good idea)
	opHandlers = {
		0x00 : lambda op, pict, bs: 0,									#nop
		0x01 : lambda op, pict, bs: bs.readUShort(),					#clipping region, ignore for now
		0x0A : lambda op, pict, bs: 8,									#pattern, ignore
		0x90 : macPictUnpackBits,
		0x91 : macPictUnpackBits,
		0x98 : macPictUnpackBits,
		0x99 : macPictUnpackBits,
		0xA0 : lambda op, pict, bs: 2									#short comment, ignore
	}

	pict.canvasWidth = pict.rect.getWidth() + MAC_PICT_ALLOW_OVERSCAN
	pict.canvasHeight = pict.rect.getHeight()
	pict.canvas = bytearray(pict.canvasWidth * pict.canvasHeight * 4)

	while not bs.checkEOF():
		op = bs.readUByte()
		if op == 0xFF:
			break #natural finish
		opOffset = bs.tell()
		if op not in opHandlers:
			print("Unhandled op: %02x"%op, "@", opOffset - 1)
			break
		opOffset = bs.tell()
		opSize = opHandlers[op](op, pict, bs)
		if opSize < 0:
			print("Op handler aborted: %02x"%op, "@", opOffset - 1)
			break
		bs.seek(opOffset + opSize, NOESEEK_ABS)

	texList.append(NoeTexture("macpict", pict.canvasWidth, pict.canvasHeight, pict.canvas, noesis.NOESISTEX_RGBA32))
		
	return 1
