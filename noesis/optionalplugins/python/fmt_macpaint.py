from inc_noesis import *
import os

MACPAINT_WIDTH = 576
MACPAINT_HEIGHT = 720
MACPAINT_DECODEPATTERNS = False #set to true to load each pattern as a separate image
MACPAINT_PATTERN_COUNT = 38

MACPAINT_ENABLE_SCRAPER = False
MACPAINT_SCRAPER_READ_SIZE = 0x10000

def registerNoesisTypes():
	handle = noesis.register("MacPaint Image", ".mpnt;.pntg")
	noesis.setHandlerTypeCheck(handle, mpCheckType)
	noesis.setHandlerLoadRGBA(handle, mpLoadRGBA)
	noesis.setHandlerWriteRGBA(handle, mpWriteRGBA)
	if MACPAINT_ENABLE_SCRAPER:
		toolHandle = noesis.registerTool("MacPaint Scraper", mpScrapeToolMethod, "Look for MacPaint files in consecutive, aligned blocks.")
		noesis.setToolFlags(toolHandle, noesis.NTOOLFLAG_CONTEXTITEM)
	return 1

class MacPaintFile:
	def __init__(self, data):
		self.data = None
		self.patterns = None
		#technically the mpnt version is a uint32, but since the expected range is small enough we use this as a hack to detect whether there's a MacBinary header
		v0 = noeUnpack(">H", data[:2])[0]
		verOffset = 128 if v0 != 0 else 0
		v1 = noeUnpack(">H", data[verOffset + 2:verOffset + 4])[0]
		if v1 > 0 and v1 < 8:
			dataOffset = verOffset + 512
			if v1 >= 2 and MACPAINT_DECODEPATTERNS:
				#pattern data follows version, see MacPaint.p/ReadWrite
				self.patterns = data[verOffset + 4 : verOffset + 4 + MACPAINT_PATTERN_COUNT * 8]
			self.data = data[dataOffset:]

def mpCheckType(data):
	if len(data) <= 512:
		return 0
	mp = MacPaintFile(data)
	if not mp.data:
		return 0
	return 1

def mpLoadRGBA(data, texList):
	mp = MacPaintFile(data)
	rgba = rapi.callExtensionMethod("macpaint_rle_decode", mp.data, MACPAINT_WIDTH, MACPAINT_HEIGHT)
	tex = NoeTexture("macpaint", MACPAINT_WIDTH, MACPAINT_HEIGHT, rgba, noesis.NOESISTEX_RGBA32)
	tex.flags |= noesis.NTEXFLAG_FILTER_NEAREST
	texList.append(tex)
	if mp.patterns:
		colorBlack = bytearray((0, 0, 0, 255))
		colorWhite = bytearray((255, 255, 255, 255))
		for patternIndex in range(0, MACPAINT_PATTERN_COUNT):
			patternOffset = patternIndex * 8
			pattern = mp.patterns[patternOffset : patternOffset + 8]
			patternRgba = bytearray()
			for y in range(0, 8):
				c = pattern[y]
				for x in range(0, 8):
					patternRgba += colorBlack if c & 0x80 else colorWhite
					c <<= 1
			patternTex = NoeTexture("macpaint_pattern%02i"%patternIndex, 8, 8, patternRgba, noesis.NOESISTEX_RGBA32)
			patternTex.flags |= noesis.NTEXFLAG_FILTER_NEAREST
			texList.append(patternTex)

	return 1

def mpWriteRGBA(data, width, height, bs):
	rgba = rapi.imageResample(data, width, height, MACPAINT_WIDTH, MACPAINT_HEIGHT)
	bs.writeBytes(noePack(">I", 1)) #write version 1 since we aren't preserving patterns
	bs.writeBytes(bytearray(508))
	bs.writeBytes(rapi.callExtensionMethod("macpaint_rle_encode", rgba, MACPAINT_WIDTH, MACPAINT_HEIGHT))
	return 1
	
def mpScrapeToolMethod(toolIndex):
	srcPath = noesis.getSelectedFile()
	if not srcPath or not os.path.exists(srcPath):
		return 0

	baseName, baseExt = os.path.splitext(srcPath)
	noesis.logPopup()
	print("Scraping file:", srcPath)
		
	noeMod = noesis.instantiateModule()
	noesis.setModuleRAPI(noeMod)
		
	foundCount = 0
	with open(srcPath, "rb") as f:
		while True:
			currentOffset = f.tell()
			tag = f.read(4)
			if not tag:
				break
			tag = noeUnpack(">I", tag)[0]
			if tag == 2 or tag == 3:
				rgba = None
				try:
					f.seek(currentOffset, os.SEEK_SET)
					data = f.read(MACPAINT_SCRAPER_READ_SIZE)
					if data:
						mp = MacPaintFile(data)
						if mp.data:
							rgba = rapi.callExtensionMethod("macpaint_rle_decode", mp.data, MACPAINT_WIDTH, MACPAINT_HEIGHT)
				except:
					rgba = None

				if rgba:
					destName = baseName + ".dump%04i.png"%foundCount
					foundCount += 1
					print("Found prospect at %08x, writing:"%currentOffset, destName)
					noesis.saveImageRGBA(destName, NoeTexture(destName, MACPAINT_WIDTH, MACPAINT_HEIGHT, rgba, noesis.NOESISTEX_RGBA32))
				
			f.seek(currentOffset + 512, os.SEEK_SET)

	noesis.freeModule(noeMod)
			
	return 0
