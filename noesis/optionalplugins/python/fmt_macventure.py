#MacVenture format support is almost entirely courtesy of information provided by Sean Kasun:
# http://seancode.com/webventure/formats.html
#this is by no means a complete implementation, and is only here to extract data from some unreleased/debug builds.
from inc_noesis import *
from fmt_macres import mcrLoadFromFile
from inc_imgtools import macEsperantoToAscii
import os

TEXT_DUMP_RESOLVE = True #if true, resolves composite strings while dumping text

def registerNoesisTypes():
	handle = noesis.register("MacVenture container", ".mcv0")
	noesis.setHandlerExtractArc(handle, mcvExtractArc)
	return 1

def mcvPassthrough(data, macRes):
	return data

def mcvDecodeGraphicAsPng(data, macRes):
	decResult = mcvDecodeGraphic(data)
	if not decResult:
		return None
	rgba, width, height = decResult
	return rapi.imageWritePNGBuffer(rgba, width, height)
	
def mcvWriteIndividual(bs, fileEntries, typeExt, macRes, dataHandler):
	for fileIndex in range(0, len(fileEntries)):
		offset, size = fileEntries[fileIndex]
		bs.seek(offset, NOESEEK_ABS)
		name = "file%04i."%fileIndex + typeExt
		data = dataHandler(bs.readBytes(size), macRes)
		if data:
			print("Writing", name)
			rapi.exportArchiveFile(name, data)

def mcvDecodeGraphic(data):
	#off in native land for the sake of speed
	return rapi.callExtensionMethod("macventure_ppic_decode", data + bytearray(0x10))

def mcvGetTextHuffTable(macRes):
	huffTable = macRes.readRefData(macRes.userBs, 0x474E524C, 0x83)
	if huffTable:
		huffBs = NoeBitStream(huffTable, NOE_BIGENDIAN)
		huffCount = huffBs.readUShort()
		huffBs.readUShort() #unused
		huffMasks = [huffBs.readUShort() for x in range(0, huffCount - 1)]
		huffLens = huffBs.readBytes(huffCount)
		huffVals = huffBs.readBytes(huffCount)
		return huffCount, huffMasks, huffLens, huffVals
	return None

def mcvDecodeString(resolveBs, resolveEntries, textBs, huffData, currentId, resolveComposite):
	decText = bytearray()
	if huffData:
		huffCount, huffMasks, huffLens, huffVals = huffData
		lenBits = 15 if textBs.readBits(1) else 7
		strSize = textBs.readBits(lenBits)
		for charIndex in range(0, strSize):
			textBs.pushOffset()
			huffTest = textBs.readUShort()
			textBs.popOffset()
			
			huffIndex = 0
			while huffIndex < huffCount - 1:
				if huffMasks[huffIndex] > huffTest:
					break
				huffIndex += 1
			textBs.readBits(huffLens[huffIndex])
			
			charVal = huffVals[huffIndex]
			if charVal == 1: #7-bit ascii
				charVal = textBs.readBits(7)

			if charVal != 2:
				decText.append(charVal)
			else:
				#composite object, just dump a marker preserving the data
				compType = textBs.readBits(1)
				valueSize = 15 if compType else 8
				compValue = textBs.readBits(valueSize)
				if resolveComposite:
					if not compType:
						markerString = "$NOUN(%i)$"%compValue
						decText += markerString.encode("ASCII")
					elif compValue != currentId:
						decText += mcvLoadString(resolveBs, resolveEntries, huffData, compValue, resolveComposite)
					else:
						decText += b"$SELF_RECURSION$"
				else:
					markerString = "$COMPOSITE(type=%i,value=%i)$"%(compType, compValue)
					decText += markerString.encode("ASCII")
	else:
		strSize = textBs.readUShort()
		inLower = False
		for charIndex in range(0, strSize):
			controlVal = textBs.readBits(5)
			charVal = None
			markerString = None
			if controlVal >= 0x01 and controlVal <= 0x1A:
				#remap to ascii a-z
				charBias = 0x60 if inLower else 0x40
				charVal = controlVal + charBias
			elif controlVal == 0x1D:
				compValue = textBs.readBits(16)
				if resolveComposite:
					if compValue & 0x8000:
						markerString = "$NOUN(%i)$"%(compValue ^ 0xFFFF)
						decText += markerString.encode("ASCII")
					elif compValue != currentId:
						decText += mcvLoadString(resolveBs, resolveEntries, huffData, compValue, resolveComposite)
					else:
						decText += b"$SELF_RECURSION$"
				else:
					markerString = "$COMPOSITE(value=%i)$"%compValue
			elif controlVal == 0x1E:
				charVal = textBs.readBits(8)
			elif controlVal == 0x1F:
				inLower = not inLower
			else:
				charMapLower = { 0x00 : " ", 0x1B : ".", 0x1C : "'" }
				charMapUpper = { 0x00 : " ", 0x1B : ",", 0x1C : "\"" }
				charMap = charMapLower if inLower else charMapUpper
				charVal = ord(charMap[controlVal])
				
			if controlVal >= 0x01 and controlVal <= 0x1E:
				inLower = True
				
			if markerString:
				decText += markerString.encode("ASCII")
			if charVal:
				decText.append(charVal)

	return decText
	
def mcvLoadString(bs, fileEntries, huffData, id, resolveComposite):
	offset, size = fileEntries[id]
	bs.seek(offset, NOESEEK_ABS)
	rawData = bs.readBytes(size)
	textBs = NoeBitStream(rawData + bytearray(0x10), NOE_BIGENDIAN)
	textBs.setByteEndianForBits(NOE_BIGENDIAN)
	return mcvDecodeString(bs, fileEntries, textBs, huffData, id, resolveComposite)
	
def mcvWriteText(bs, fileEntries, typeExt, macRes, dataHandler):
	huffData = mcvGetTextHuffTable(macRes)
	
	print("Decompressing text.")
	#write it all in one large txt file instead of individual files
	allText = bytearray()
	for fileIndex in range(0, len(fileEntries)):
		allText += bytearray(("$STR_%04i$	"%fileIndex).encode("ASCII")) + mcvLoadString(bs, fileEntries, huffData, fileIndex, TEXT_DUMP_RESOLVE) + b"\n\n"

	name = "all_text." + typeExt
	print("Writing", name)
	rapi.exportArchiveFile(name, allText)

def mcvLoadGfxFromId(gfxIndex, gfxBs, gfxEntries):
	if gfxIndex >= len(gfxEntries):
		return None
	gfxOffset, gfxSize = gfxEntries[gfxIndex]
	if gfxSize < 2:
		return None

	gfxBs.seek(gfxOffset, NOESEEK_ABS)
	gfxData = gfxBs.readBytes(gfxSize)
	if gfxSize == 2:
		refId = noeUnpack(">H", gfxData)[0]
		return mcvLoadGfxFromId(refId, gfxBs, gfxEntries)
	return mcvDecodeGraphic(gfxData)

def mcvWriteObjects(bs, fileEntries, typeExt, macRes, dataHandler):
	textHuffData = mcvGetTextHuffTable(macRes)
	genSettingsData = macRes.readRefData(macRes.userBs, 0x474E524C, 0x80)
	if not genSettingsData:
		print("Error: Required resource not found for object dump.")
		return

	#text data required
	txtData = rapi.loadPairedFile("MacVenture Text", ".mcv0")
		
	try:
		gfxData = rapi.loadPairedFile("MacVenture Graphics", ".mcv0")
	except:
		gfxData = None

	try:
		gameData = rapi.loadPairedFile("MacVenture Game", ".mcv0")
	except:
		gameData = None
		
	if not gameData:
		print("Warning: Game data isn't required, but constant attributes will be incorrect.")
		
	txtBs = NoeBitStream(txtData + bytearray(0x10), NOE_BIGENDIAN)
	txtBs.setByteEndianForBits(NOE_BIGENDIAN)
	txtEntries = mcvLoadFileEntries(txtBs, len(txtData))
	
	if gfxData:
		gfxBs = NoeBitStream(gfxData + bytearray(0x10), NOE_BIGENDIAN)
		gfxBs.setByteEndianForBits(NOE_BIGENDIAN)
		gfxEntries = mcvLoadFileEntries(gfxBs, len(gfxData))
	else:
		gfxEntries = []

	sbs = NoeBitStream(genSettingsData, NOE_BIGENDIAN)
	objectCount = sbs.readUShort()
	if objectCount < len(fileEntries):
		print("Error: Object count does not match count provided in Mac Resource.")
		return
	globalCount = sbs.readUShort()
	cmdCount = sbs.readUShort()
	attrCount = sbs.readUShort()
	groupCount = sbs.readUShort()
	sbs.seek(18, NOESEEK_REL) #don't care about the stuff in between here
	attrIndices = sbs.readBytes(attrCount)
	attrMasks = [sbs.readUShort() for x in range(0, attrCount)]
	attrShifts = sbs.readBytes(attrCount)

	constAttrs = []

	if gameData:
		expectedSize = groupCount * objectCount * 2 + globalCount * 2
		if len(gameData) < expectedSize:
			print("Warning: Game data is not large enough, you may have selected the wrong file:", len(gameData), "vs", expectedSize)
		else:
			gameBs = NoeBitStream(gameData, NOE_BIGENDIAN)
			for groupIndex in range(0, groupCount):
				groupAttrs = [gameBs.readUShort() for x in range(0, objectCount)]
				constAttrs.append(groupAttrs)

	knownAttrs = {
		0x00 : "Parent Object",
		0x01 : "X position in window",
		0x02 : "Y position in window",
		0x03 : "Invisible flag",
		0x04 : "Unclickable flag",
		0x05 : "Undraggable flag",
		0x06 : "Container Open",
		0x07 : "Prefixes",
		0x08 : "Is Exit",
		0x09 : "Exit X",
		0x0A : "Exit Y",
		0x0B : "Hidden Exit",
		0x0C : "Other Door",
		0x0D : "Is Open",
		0x0E : "Is Locked",
		0x10 : "Weight",
		0x11 : "Size",
		0x13 : "Has Description",
		0x14 : "Is Door",
		0x16 : "Is Container",
		0x17 : "Is Operable",
		0x18 : "Is Enterable",
		0x19 : "Is Edible"
	}
	for objectIndex in range(0, objectCount):
		objOffset, objSize = fileEntries[objectIndex]
		attribs = []
		for attrIndex in range(0, attrCount):
			idx = attrIndices[attrIndex]
			if idx & 0x80:
				#per-object attribute
				attrOffset = (idx & 0x7F) * 2
				if attrOffset < objSize:
					bs.seek(objOffset + attrOffset, NOESEEK_ABS)
					attrVal = bs.readUShort()
				else:
					attrVal = 0
			else:
				attrVal = constAttrs[idx][objectIndex] if idx < len(constAttrs) else 0
			attrVal &= attrMasks[attrIndex]
			attrVal >>= attrShifts[attrIndex]
			attribs.append(attrVal)
			
		objInfo = bytearray()
		objName = mcvLoadString(txtBs, txtEntries, textHuffData, objectIndex, True)
		objDesc = mcvLoadString(txtBs, txtEntries, textHuffData, objectIndex + objectCount, True)

		pathBase = "%04i"%objectIndex
		if len(objName) > 0:
			pathBase += " - " + macEsperantoToAscii(objName)
		
		objInfo += b"Name: " + objName + b"\n"
		objInfo += b"Description: " + objDesc + b"\n"
		objInfo += b"Attributes:\n"
		for attrIndex in range(0, len(attribs)):
			attribDesc = "	%02i - "%attrIndex
			if attrIndex in knownAttrs:
				attribDesc += knownAttrs[attrIndex] + " - "
			attribDesc += "%i\n"%attribs[attrIndex]
			objInfo += attribDesc.encode("ASCII")
		
		infoPath = pathBase + ".txt"
		print("Writing", infoPath)
		rapi.exportArchiveFile(infoPath, objInfo)
		
		if len(gfxEntries) > 0:
			gfxIndex = objectIndex * 2
			gfxMaskIndex = gfxIndex + 1
			gfxData = mcvLoadGfxFromId(gfxIndex, gfxBs, gfxEntries)
			gfxMaskData = mcvLoadGfxFromId(gfxMaskIndex, gfxBs, gfxEntries)
			if not gfxData and gfxMaskData:
				gfxData = gfxMaskData

			if gfxData:
				rgba, width, height = gfxData
				if gfxMaskData:
					maskRgba, maskWidth, maskHeight = gfxMaskData
					matchWidth = min(width, maskWidth)
					matchHeight = min(height, maskHeight)
					for y in range(0, matchHeight):
						for x in range(0, matchWidth):
							rgba[(y * width + x) * 4 + 3] = 255 - maskRgba[(y * maskWidth + x) * 4]
				gfxPath = pathBase + ".png"
				print("Writing", gfxPath)
				rapi.exportArchiveFile(gfxPath, rapi.imageWritePNGBuffer(rgba, width, height))				

def mcvWriteTitleOrDiploma(bs, fileEntries, name, typeExt, macRes):
	#these things are just macpaint files when not ppic resources, rename to mpnt and the noesis macpaint script can load them
	res = mcrLoadFromFile(bs, len(bs.getBuffer()), False)
	if not res:
		print("Error: Not a Mac Resource file as expected.")
		return

	ppicType = res.findType(0x50504943)
	if not ppicType:
		print("Error: No PPIC resource.")
		return
		
	gfxCount = 0
	for ref in ppicType.refList:
		dataOffset = res.resDataOffset + ref.dataOffset
		bs.seek(dataOffset, NOESEEK_ABS)
		dataSize = bs.readUInt()
		data = bs.readBytes(dataSize)

		pngData = mcvDecodeGraphicAsPng(data, macRes)
		if pngData:
			gfxPath = "file%04i."%gfxCount + typeExt
			gfxCount += 1
			print("Writing", gfxPath)
			rapi.exportArchiveFile(gfxPath, pngData)
	
def mcvWriteTitle(bs, fileEntries, typeExt, macRes, dataHandler):
	mcvWriteTitleOrDiploma(bs, fileEntries, "title", typeExt, macRes)

def mcvWriteDiploma(bs, fileEntries, typeExt, macRes, dataHandler):
	mcvWriteTitleOrDiploma(bs, fileEntries, "diploma", typeExt, macRes)

def mcvLoadRes():
	try:
		resData = rapi.loadPairedFile("Mac Resource File", ".appl")
		if resData:
			bs = NoeBitStream(resData, NOE_BIGENDIAN)
			macRes = mcrLoadFromFile(bs, len(resData), False)
			if macRes:
				macRes.userBs = bs
				return macRes
	except:
		pass
	return None
	
def mcvLoadFileEntries(bs, fileLen):
	fileEntries = []
	
	containerInfo = bs.readUInt()
	if not containerInfo & 0x80000000:
		objectSize = containerInfo
		offset = 4
		while (offset + objectSize) <= fileLen:
			fileEntries.append((offset, objectSize))
			offset += objectSize				
	else:
		headerOffset = containerInfo & 0x7FFFFFFF
		bs.seek(headerOffset, NOESEEK_ABS)
		objectCount = bs.readUShort()
		huffMasks = [bs.readUShort() for x in range(0, 15)]
		huffLens = bs.readBytes(16)
		groupBaseOffset = bs.tell()
		
		objectOffset = 0
		for objectIndex in range(0, objectCount):
			if not objectIndex & 0x3F:
				#group boundary
				bs.seek(groupBaseOffset + (objectIndex >> 6) * 6, NOESEEK_ABS)
				bitOffset = bs.readUInt24()
				objectOffset = bs.readUInt24()
				bs.seek(headerOffset + (bitOffset >> 3), NOESEEK_ABS)
				bs.readBits(bitOffset & 7)
				
			bs.pushOffset()
			huffTest = bs.readUShort()
			bs.popOffset()
			
			huffIndex = 0
			while huffIndex < 15:
				if huffMasks[huffIndex] > huffTest:
					break
				huffIndex += 1
			huffLen = huffLens[huffIndex]
			#increment the actual number of bits we needed to cover the test value
			bs.readBits(huffLen & 0x0F)

			huffLen >>= 4
			objectSize = 0
			#now read the actual value
			if huffLen > 0:
				huffLen -= 1
				if huffLen > 0:
					objectSize = bs.readBits(huffLen)
				objectSize |= (1 << huffLen)
					
			fileEntries.append((4 + objectOffset, objectSize))						
			objectOffset += objectSize
			
	return fileEntries

def mcvExtractArc(fileName, fileLen, justChecking):
	if fileLen <= 4:
		return 0
		
	#not really bothering with good validation, just rely on the extension
	if justChecking:
		return 1
		
	with open(fileName, "rb") as f:
		#just chomp the whole thing into memory if we're here to actually do work
		bs = NoeBitStream(f.read() + bytearray(0x10), NOE_BIGENDIAN)
		bs.setByteEndianForBits(NOE_BIGENDIAN)
		
		dirPath, filePath = os.path.split(fileName)
		testPath = filePath.lower()
		arcTypes = (
			("graphic", "mcv_gfx"),
			("sound", "mcv_snd"),
			("text", "mcv_txt"),
			("filter", "mcv_flt"),
			("object", "mcv_obj"),
			("game", "mcv_gam"),
			("title", "mcv_ttl"),
			("diploma", "mcv_dpl"),			
		)
		#possible todo - handle sound (since data in unreleased games doesn't line up with Sean's observations, need to actually do some digging into the disassembly)
		conversionMap = {
			"mcv_gfx" : ("png", mcvDecodeGraphicAsPng, mcvWriteIndividual, False, True),
			"mcv_txt" : ("txt", mcvPassthrough, mcvWriteText, True, True),
			"mcv_obj" : ("various", mcvPassthrough, mcvWriteObjects, True, True),
			"mcv_ttl" : ("png", mcvPassthrough, mcvWriteTitle, False, False),
			"mcv_dpl" : ("png", mcvPassthrough, mcvWriteDiploma, False, False)
		}

		parseEntries = True
		macRes = None
		dataHandler = mcvPassthrough
		writeHandler = mcvWriteIndividual
		
		writeExt = None
		for typeKey, typeExt in arcTypes:
			if typeKey in testPath:
				writeExt = typeExt
				break

		if not writeExt:
			print("Warning: No recognized content type based on archive filename, defaulting to bin.")
			writeExt = "mcv_bin"
		elif writeExt in conversionMap:
			#this type supports conversion on extraction
			convExt, convData, convWrite, needRes, needEntries = conversionMap[writeExt]
			canConvert = True
			if needRes:
				#translation requires the resource file
				macRes = mcvLoadRes()
				if not macRes:
					print("Warning: This type supports conversion, but the required resource file was not loaded. Writing raw binary instead.")
					canConvert = False
			if canConvert:
				parseEntries = needEntries
				writeExt = convExt
				dataHandler = convData
				writeHandler = convWrite
			
		fileEntries = mcvLoadFileEntries(bs, fileLen) if parseEntries else []
		writeHandler(bs, fileEntries, writeExt, macRes, dataHandler)

	return 1
