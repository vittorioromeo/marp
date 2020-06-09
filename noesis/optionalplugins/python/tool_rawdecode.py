from inc_noesis import *
import os

#format may be:
# - rgba bit counts such as r8, r5g6b5, r8g8b8a8, r8g8b8p8, ... (p means increment but ignore this many bits)
# - block compression modes such as bc1, bc2, bc3, ...
# - astc modes such as astc4x4, astc6x6, ...
# - pvrtc modes such as pvrtc_2, pvrtc_4, pvrtc2_2, pvrtc2_4
# - etc modes such as etc_rgb, etc_rgb1, etc_rgba, ...

RAWDECODE_STRING = "64;64;r8;0"

ASSUME_PVRTC_LINEAR = False #set to false for morton ordering, true for linear
ENDIAN_SWAP_SIZE = 0 #set to > 1 to perform an endian swap on raw data, commonly required with certain data types on ps3/360
SKIP_ELEM_BYTES = (0, 0)
KEEP_DECODED_IMAGE = False #set to true in order to prompt for destination path instead of treating as a temporary file

ASSUME_BC5_IS_NORMAL = True
NORMAL_SPLAYED_Z_FACTOR = 0.0

def registerNoesisTypes():
	handle = noesis.registerTool("Raw image decode", rdToolMethod, "Perform a raw image decode.")
	noesis.setToolFlags(handle, noesis.NTOOLFLAG_CONTEXTITEM)
	return 1

def rdGetOptions(optionString):
	try:
		l = optionString.split(";")
		return int(l[0]), int(l[1]), l[2], int(l[3])
	except:
		return 0, 0, None, 0
	
def rdValidateOptionString(inVal):
	options = rdGetOptions(inVal)
	if not options[0]:
		return "Invalid format string."
	return None
	
def rdToolMethod(toolIndex):
	srcName = noesis.getSelectedFile()
	if not srcName or not os.path.exists(srcName):
		noesis.messagePrompt("Selected file isn't readable through the standard filesystem.")
		return 0

	global RAWDECODE_STRING
	optionString = noesis.userPrompt(noesis.NOEUSERVAL_STRING, "Option String", "Enter the decode specification string in the format of width;height;format;offset.", RAWDECODE_STRING, rdValidateOptionString)
	if not optionString:
		return 0
	RAWDECODE_STRING = optionString
	
	width, height, format, offset = rdGetOptions(optionString)
	if not format:
		return 0

	if KEEP_DECODED_IMAGE:
		defaultSavePath = os.path.splitext(srcName)[0] + "_rawdecode.png"	
		dstName = noesis.userPrompt(noesis.NOEUSERVAL_SAVEFILEPATH, "Save File", "Select destination for decoded image.", defaultSavePath, None)
		if not dstName:
			return 0
	else:
		dstName = noesis.getScenesPath() + "rawdecode_results.png"

	noeMod = noesis.instantiateModule()
	noesis.setModuleRAPI(noeMod)
		
	rawData = rapi.loadIntoByteArray(srcName)
	dataAtOffset = rawData[offset:]
	if ENDIAN_SWAP_SIZE > 0:
		dataAtOffset = rapi.swapEndianArray(dataAtOffset, ENDIAN_SWAP_SIZE)
	skipBytes, elemBytes = SKIP_ELEM_BYTES
	if skipBytes > 0 and elemBytes > skipBytes:
		offset = 0
		usedElemSize = elemBytes - skipBytes
		newData = bytearray()
		while offset < len(dataAtOffset):
			newData += dataAtOffset[offset : offset + usedElemSize]
			offset += elemBytes
		dataAtOffset = newData
	
	if format.startswith("bc"):
		bcModeString = format[2:].lower()
		bcModes = {
			"1" : noesis.NOESISTEX_DXT1,
			"2" : noesis.NOESISTEX_DXT3,
			"3" : noesis.NOESISTEX_DXT5,
			"4" : noesis.FOURCC_ATI1,
			"4s" : noesis.FOURCC_ATI1,
			"5" : noesis.FOURCC_ATI2,
			"5s" : noesis.FOURCC_ATI2,
			"6" : noesis.FOURCC_BC6H,
			"6s" : noesis.FOURCC_BC6S,
			"7" : noesis.FOURCC_BC7
		}
		if bcModeString not in bcModes:
			print("Unimplemented BC:", bcModeString, "Treating as BC1.")
			bcModeString = "1"
		bcMode = bcModes[bcModeString]
		addlFlags = 0
		if bcMode == noesis.FOURCC_ATI1 or bcMode == noesis.FOURCC_ATI2:
			if not ASSUME_BC5_IS_NORMAL:
				addlFlags |= 1
			if bcModeString.endswith("s"):
				addlFlags |= 2
		rgba = rapi.imageDecodeDXT(dataAtOffset, width, height, bcMode, NORMAL_SPLAYED_Z_FACTOR, addlFlags)
	elif format.startswith("astc"):
		blockSize = [int(i) for i in format[4:].split("x")]
		blockWidth, blockHeight = blockSize
		rgba = rapi.callExtensionMethod("astc_decoderaw32", dataAtOffset, blockWidth, blockHeight, 1, width, height, 1)
	elif format.startswith("pvrtc"):
		decodeFlags = noesis.PVRTC_DECODE_PVRTC2 if format.startswith("pvrtc2") else 0
		bpp = int(format[format.rfind("_") + 1:])
		if ASSUME_PVRTC_LINEAR:
			decodeFlags |= noesis.PVRTC_DECODE_LINEARORDER
		rgba = rapi.imageDecodePVRTC(dataAtOffset, width, height, bpp, decodeFlags)
	elif format.startswith("etc"):
		formatString = format[format.rfind("_") + 1:]
		rgba = rapi.callExtensionMethod("etc_decoderaw32", dataAtOffset, width, height, formatString)
	else:
		rgba = rapi.imageDecodeRaw(dataAtOffset, width, height, format)
		
	tex = NoeTexture(dstName, width, height, rgba, noesis.NOESISTEX_RGBA32)
	
	if not noesis.saveImageRGBA(dstName, tex):
		noesis.messagePrompt("Error writing decoded image.")
		return 0

	if KEEP_DECODED_IMAGE:
		noesis.openFile(dstName)
	else:
		noesis.openAndRemoveTempFile(dstName)
		
	noesis.freeModule(noeMod)

	return 0
