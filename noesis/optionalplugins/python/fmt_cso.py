from inc_noesis import *

def registerNoesisTypes():
	handle = noesis.register("CISO Image", ".cso")
	noesis.setHandlerExtractArc(handle, csoExtractArc)
	return 0
	
def csoExtractArc(fileName, fileLen, justChecking):
	if fileLen < 24:
		return 0
		
	with open(fileName, "rb") as f:
		bs = NoeFileStream(f)
		bs.seek(0, NOESEEK_ABS)
		id = bs.readUInt()
		headerSize = bs.readUInt()
		decompDataSize = bs.readUInt64()
		decompBlockSize = bs.readUInt()
		ver = bs.readUByte()
		offsetShift = bs.readUByte()
		if id != 0x4F534943 or decompDataSize <= 0 or decompBlockSize <= 0 or ver != 1:
			return 0
			
		if justChecking:
			return 1

		exportName = "decompressed.iso"
		
		bs.seek(headerSize if headerSize > 0 else 24, NOESEEK_ABS)
		
		blockCount = decompDataSize // decompBlockSize
		tableEntryCount = blockCount + 1
		blockTable = noeUnpack("<" + "I" * tableEntryCount, bs.readBytes(tableEntryCount * 4))
		
		print("Writing", exportName)
		absPath = rapi.exportArchiveFileGetName(exportName)
		with open(absPath, "wb") as fw:
			for blockIndex in range(0, blockCount):
				tableEntry = blockTable[blockIndex]
				
				blockOffset = tableEntry & 0x7FFFFFFF
				bs.seek(blockOffset << offsetShift, NOESEEK_ABS)
				
				isCompressed = (tableEntry & 0x80000000) == 0
				if isCompressed:
					nextOffset = blockTable[blockIndex + 1] & 0x7FFFFFFF
					compBlock = bs.readBytes((nextOffset - blockOffset) << offsetShift)
					fw.write(rapi.decompInflate(compBlock, decompBlockSize, -15))
				else:
					fw.write(bs.readBytes(decompBlockSize))

		return 1
