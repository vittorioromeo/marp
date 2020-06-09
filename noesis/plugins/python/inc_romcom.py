#common routines for dealing with rom images and romantic comedies
from inc_noesis import *
import os

ReadRomImageFlag_None = 0
ReadRomImageFlag_Interleave = (1 << 0)
ReadRomImageFlag_EndianSwap_Word = (1 << 1)
ReadRomImageFlag_EndianSwap_DWord = (1 << 2)

def readRomImages(imageBasePath, imageSet, imageSize, flags = ReadRomImageFlag_None, printStatus = False):
	imageCount = len(imageSet)
	data = bytearray()
	for imageIndex in range(0, imageCount):
		imagePath = imageSet[imageIndex]
		imageFilePath = os.path.join(imageBasePath, imagePath)
		imageFileSize = os.path.getsize(imageFilePath)
		if imageFileSize != imageSize:
			if printStatus:
				print("Bad/no image -", imageFileSize, "-", imageFilePath)
			return None
		if printStatus:
			print("Loading", imageFilePath)
		with open(imageFilePath, "rb") as f:
			data += f.read()
			
	if flags & ReadRomImageFlag_Interleave:
		data = noesis.interleaveUniformBytes(data, 1, imageSize)
	if flags & ReadRomImageFlag_EndianSwap_Word:
		data = noesis.swapEndianArray(data, 2)
	if flags & ReadRomImageFlag_EndianSwap_DWord:
		data = noesis.swapEndianArray(data, 4)
		
	return data

#snes address to file functions assume a headerless image

def snesHiRomPtrToFileOffset(addr):
	if addr == 0:
		return 0
	if addr >= 0xC00000:
		return addr - 0xC00000
	#assume we're using the other set of linear banks
	return addr - 0x400000

def snesLoRomPtrToFileOffset(addr):
	if addr == 0:
		return 0
	if addr >= 0x800000:
		addr -= 0x800000
	bank = (addr >> 16)
	if not bank & 1:
		addr -= 0x8000
	bank >>= 1
	return (bank << 16) | (addr & 0xFFFF)

def snesFileOffsetToLoRomPtr(offset, bankRebase = 0x80):
	if offset == 0:
		return 0
	bank = offset >> 16
	addr = offset & 0xFFFF
	bank <<= 1
	if addr >= 0x8000:
		bank += 1
		addr -= 0x8000

	bank += bankRebase
	addr += 0x8000
	
	return (bank << 16) | addr
