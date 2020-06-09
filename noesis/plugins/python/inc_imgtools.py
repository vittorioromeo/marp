from inc_noesis import *
import os

NoeImg_TrackType_Data = 0
NoeImg_TrackType_Audio = 1

class NoeImgTrack:
	def __init__(self, stream, index, baseLba, sectorSize, userSize, userOffset, trackType = NoeImg_TrackType_Data, streamOwner = True, imageOffset = 0):
		self.index = index
		self.stream = stream
		self.baseLba = baseLba
		self.sectorSize = sectorSize
		self.userSize = userSize
		self.userOffset = userOffset
		self.trackType = trackType
		self.streamOwner = streamOwner
		self.imageOffset = imageOffset
		
	def close(self):
		if self.streamOwner and self.stream:
			self.stream.close()
		self.stream = None
		self.streamOwner = False
			
class NoeImgReader:
	def __init__(self, tracks):
		self.tracks = sorted(tracks, key=noeCmpToKey(lambda a,b: a.baseLba - b.baseLba))
		self.currentSector = 0
		self.currentTrack = 0
		
	def setSector(self, sectorIndex):
		self.currentTrack = len(self.tracks) - 1
		self.currentSector = sectorIndex
		while self.currentTrack > 0:
			t = self.tracks[self.currentTrack]
			if sectorIndex >= t.baseLba:
				break
			self.currentTrack -= 1
		t = self.tracks[self.currentTrack]
		if sectorIndex >= t.baseLba:
			f = t.stream
			f.seek((sectorIndex - t.baseLba) * t.sectorSize + t.imageOffset, os.SEEK_SET)
		
	def readSectors(self, sectorCount):
		out = bytearray()
		t = self.tracks[self.currentTrack]
		f = t.stream
		nextT = self.tracks[self.currentTrack + 1] if self.currentTrack < (len(self.tracks) - 1) else None
		for i in range(0, sectorCount):
			s = f.read(t.sectorSize)
			if s:
				out += s[t.userOffset : t.userOffset + t.userSize]
			else: #if not s, we ran off the last track or there's a gap between tracks, so pad with 0
				out += bytearray(t.userSize)
				
			self.currentSector += 1
			if nextT and self.currentSector >= nextT.baseLba:
				#hop to the next track
				t = nextT
				f = t.stream
				self.currentTrack += 1
				nextT = self.tracks[self.currentTrack + 1] if self.currentTrack < (len(self.tracks) - 1) else None

		return out

	def readBytes(self, size):
		t = self.tracks[self.currentTrack]	
		sectorCount = (size + (t.userSize - 1)) // t.userSize
		rawData = self.readSectors(sectorCount)
		return rawData[:size]

	def readBytesAtOffset(self, offset, size):
		t = self.tracks[self.currentTrack]
		
		sectorIndex = offset // t.userSize
		sectorOffset = offset % t.userSize
		self.setSector(sectorIndex)
		
		sectorCount = ((size + sectorOffset) + (t.userSize - 1)) // t.userSize
		rawData = self.readSectors(sectorCount)
		if rawData:
			return rawData[sectorOffset : sectorOffset + size]
		return None
		
	def readFileSystemVolume(self, trackIndex = 0):
		if self.containsIso9660(trackIndex):
			return self.readIso9660(trackIndex)
		#potentially add other filesystem support here
		return None
		
	def readFileData(self, imgFile):
		data = bytearray()
		for partIndex in range(0, len(imgFile.lbas)):
			partLba = imgFile.lbas[partIndex]
			partSize = imgFile.sizes[partIndex]
			partOffset = imgFile.offsets[partIndex]
			self.setSector(partLba)
			partData = self.readBytes(partSize)
			if partData:
				data += partData[partOffset:]
		return data
		
	def trackByIndex(self, trackIndex):
		for track in self.tracks:
			if track.index == trackIndex:
				return track
		return None
		
	#convert to lba, size, offset
	def convertOffsetsAndSizes(self, offsetsAndSizes, maxSize, trackIndex = 0):
		t = self.trackByIndex(trackIndex)
		if not t:
			return False
		lbas = []
		sizes = []
		offsets = []
		totalSize = 0

		for partOffset, partSize in offsetsAndSizes:
			lba = partOffset // t.userSize
			offset = partOffset % t.userSize
			size = partSize
			totalSize += size
			#if necessary, clip part size to ensure we stay within the actual file size
			if maxSize >= 0 and totalSize > maxSize:
				size = max(0, size - (totalSize - maxSize))
				totalSize = maxSize
			lbas.append(lba)
			sizes.append(size)
			offsets.append(offset)

		return lbas, sizes, offsets

	def containsIso9660(self, trackIndex = 0):
		t = self.trackByIndex(trackIndex)
		if not t:
			return False
			
		previousSector = self.currentSector
		r = False
		try:
			self.setSector(t.baseLba + 16)
			data = self.readSectors(1)
			if data:
				id = data[1:6]
				if id == "CD001".encode("ASCII"):
					#could do further validation, but for now consider this good enough
					r = True
		except:
			pass
	
		#restore the previous position
		self.setSector(previousSector)
		return r
		
	def readIso9660(self, trackIndex = 0, volumeDescType = 1):
		t = self.trackByIndex(trackIndex)
		if not t:
			return None
			
		previousSector = self.currentSector
		r = None

		self.setSector(t.baseLba + 16)
		foundVolume = False
		while not foundVolume:
			volDesc = Iso9660VolumeDescriptor(self.readSectors(1))
			if volDesc.type == volumeDescType:
				foundVolume = True
				break
			elif volDesc.type == 0xFF:
				break
				
		if foundVolume:
			if volDesc.blockSize != t.userSize:
				print("Warning: ISO-9660 logical block size != track's user data size:", volDesc.blockSize, "vs", t.userSize)
			rootRecord = volDesc.rootRecord
			if not (rootRecord.flags & Iso9660_DirFlag_Directory):
				print("Warning: Expected root record to be a directory.")

			files = []
			processRecords = [rootRecord]
			while len(processRecords) > 0:
				record = processRecords.pop()
				if record.flags & Iso9660_DirFlag_Directory:
					self.setSector(record.dataLba)
					recordData = self.readSectors(volDesc.sizeToSectorCount(record.dataSize))
					if recordData:
						recordBs = NoeBitStream(recordData)
						while recordBs.tell() < record.dataSize:
							newRecord = Iso9660Record(recordBs, record)
							if newRecord.recordSize == 0:
								break
							if not newRecord.isSpecial():
								#note that we don't track directory records, so empty directories are ignored entirely
								processRecords.append(newRecord)
				else:
					imgFile = NoeImgFile(record.getFullPath(), [record.dataLba], [record.dataSize], [0])
					imgFile.createDate = repr(record.recDate)
					files.append(imgFile)
					
			r = NoeImgVolume(volDesc.volId, repr(volDesc.createDate), repr(volDesc.modDate), files)
			
		#restore the previous position
		self.setSector(previousSector)
		return r
		
	def containsHFS(self, trackIndex = 0, userOffset = 1024):
		t = self.trackByIndex(trackIndex)
		if not t:
			return False
			
		previousSector = self.currentSector
		r = False
		try:
			data = self.readBytesAtOffset(userOffset, 512)
			if data:
				id = noeUnpack(">H", data[:2])[0]
				#possible todo - support h+/hx (id 0x482B / 0x4858), but would need to get some images to test
				if id == HfsVersion_Hfs or id == HfsVersion_Mfs:
					#as with iso9660, could stand to have some extra validation here in the case that this ever needs to hold up across varied data
					r = True
		except:
			pass
	
		#restore the previous position
		self.setSector(previousSector)
		return r
		
	def readHFS(self, trackIndex = 0, userOffset = 1024, provideExtensions = True):
		t = self.trackByIndex(trackIndex)
		if not t:
			return None
			
		previousSector = self.currentSector
		r = None
		
		mdbData = self.readBytesAtOffset(userOffset, 512)
		mdb = HfsMasterDirectoryBlock(self, mdbData, t.userSize, userOffset, provideExtensions)
		mdb.populateRecordData()
		files = mdb.createNoesisFiles()
		if len(files) > 0:
			#possible todo - convert and pass volume dates through properly
			r = NoeImgVolume(mdb.volName, "", "", files)

		#restore the previous position
		self.setSector(previousSector)
		return r
				
	def close(self):
		for track in self.tracks:
			track.close()
		
class NoeImgFile:
	def __init__(self, path, lbas, sizes, offsets, flags = 0):
		self.path = path
		self.lbas = lbas
		self.sizes = sizes
		self.offsets = offsets
		self.flags = flags
		self.createDate = ""
		self.modifyDate = ""
		
class NoeImgVolume:
	def __init__(self, volId, createDate, modifyDate, files):
		self.volId = volId
		self.createDate = createDate
		self.modifyDate = modifyDate
		self.files = files
		self.fileDict = None
		
	#assumes case-insensitive path
	def findFile(self, path):
		if not self.fileDict:
			self.fileDict = {}
			for file in self.files:
				self.fileDict[file.path.lower()] = file
				
		lPath = path.lower()
		if lPath not in self.fileDict:
			return None
		return self.fileDict[lPath]

#hfs support is not well tested, and was written only using the following as reference:
# https://developer.apple.com/library/archive/documentation/mac/pdf/Files/File_Manager.pdf
#mfs support was just guessed at based on a few samples i have on hand. no guarantees on any of this!

HfsVersion_Hfs = 0x4244
HfsVersion_Mfs = 0xD2D7

HfsTreeType_Catalog = 0x00
HfsTreeType_Extents = 0x01

HfsNodeType_Index = 0x00
HfsNodeType_Header = 0x01
HfsNodeType_Map = 0x02
HfsNodeType_Leaf = 0xFF

HfsCatDataType_DirRecord = 0x01
HfsCatDataType_FileRecord = 0x02
HfsCatDataType_DirThreadRecord = 0x03
HfsCatDataType_FileThreadRecord = 0x04

HfsForkType_Data = 0x00
HfsForkType_Resource = 0xFF
HfsForkFlags_Data = 0x01
HfsForkFlags_Res = 0x02

HfsFileId_Extents = 0x03
HfsFileId_Catalog = 0x04

MfsRecordFlag_Valid = 0x80

#possible todo - proper esperanto to unicode mapping
HfsEsperantoToAscii = (
	"A", "A", "C", "E", "N", "O", "U", "a", "a", "a", "a", "a", "a", "c", "e", "e",
	"e", "e", "i", "i", "i", "i", "n", "o", "o", "o", "o", "o", "u", "u", "u", "u",
	"+", "*", "c", "_", "_", "-", "_", "B", "_", "_", "_", "\"", "'", "_", "_", "_",
	"C", "_", "_", "_", "c", "_", "G", "g", "H", "h", "J", "j", "S", "s", "_", "_",
	"U", "u", "_", "C", "f", "c", "G", "_", "_", "_", " ", "A", "A", "O", "_", "_",
	"-", "-", "\"", "\"", "'", "'", "/", "_", "y", "Y", "G", "g", "I", "i", "S", "s",
	"_", "-", ",", ",", "%", "A", "E", "A", "E", "E", "I", "I", "I", "I", "O", "O",
	"g", "O", "U", "U", "U", "_", "^", "~", "_", "_", "'", "Z", ".", "z", "h", "_"
)

class HfsMasterDirectoryBlock:
	def __init__(self, img, data, sectorSize, mdbOffset, provideExtensions):
		bs = NoeBitStream(data, NOE_BIGENDIAN)
		self.id = bs.readUShort()
		self.catNodes = []
		self.flatRecords = []
		self.extDict = {}
		self.resExtDict = {}
		self.img = img
		self.sectorSize = sectorSize
		self.provideExtensions = provideExtensions

		self.version = 0
		self.crDate = bs.readUInt()
		self.modDate = bs.readUInt()
		self.attrib = bs.readUShort()
		self.rootFileCount = bs.readUShort()
		if self.id == HfsVersion_Mfs:
			self.rootDirBlock = bs.readUShort()
			self.rootDirBlockCount = bs.readUShort()
		else:
			self.volBmBlock = bs.readUShort()
			self.allocPtr = bs.readUShort()
		self.allocBlockCount = bs.readUShort()
		self.allocBlockSize = bs.readUInt()
		self.dataClumpSize = bs.readUInt()
		self.rsrcClumpSize = self.dataClumpSize
		self.firstAllocBlock = bs.readUShort()
		self.nextUnusedCatNode = bs.readUInt()
		self.unusedAllocBlockCount = bs.readUShort()
		volNameData = bs.readBytes(28)
		volNameSize = volNameData[0]
		self.volName = self.decodeString(volNameData[1 : 1 + volNameSize])
		if self.id == HfsVersion_Mfs:
			self.blockMapOffset = mdbOffset + bs.tell()
			self.blockSize = self.sectorSize #self.allocBlockSize
		else:
			self.volBkDate = bs.readUInt()
			self.volSeqNum = bs.readUShort()
			self.volWriteCount = bs.readUInt()
			self.xtClumpSize = bs.readUInt()
			self.catClumpSize = bs.readUInt()
			self.rootDirCount = bs.readUShort()
			self.volFileCount = bs.readUInt()
			self.volDirCount = bs.readUInt()
			self.finderInfo = [bs.readUInt() for x in range(0, 8)]
			self.vcSize = bs.readUShort()
			self.vbSize = bs.readUShort()
			self.cvSize = bs.readUShort()
			self.extFileSize = bs.readUInt()
			self.extExtRec = HfsExtDataRec(bs)
			self.catFileSize = bs.readUInt()
			self.catExtRec = HfsExtDataRec(bs)
			
		self.sectorsPerBlock = max(self.allocBlockSize // sectorSize, 1)
		
	def populateRecordData(self):
		if self.id == HfsVersion_Mfs:
			self.blockMap = []
			blockMapSize = (self.allocBlockCount * 12 + 7) // 8
			blockMapData = self.img.readBytesAtOffset(self.blockMapOffset, blockMapSize)
			for blockIndex in range(0, self.allocBlockCount):
				bitOffset = blockIndex * 12
				byteOffset = bitOffset // 8
				if bitOffset & 7:
					entry = (blockMapData[byteOffset] & 0xF) << 8
					entry |= blockMapData[byteOffset + 1]
				else:
					entry = (blockMapData[byteOffset] << 4)
					entry |= ((blockMapData[byteOffset + 1] & 0xF0) >> 4)
				self.blockMap.append(entry)
			
			#it seems the directory must be contiguous as the blockmap doesn't include directory blocks
			dirBs = NoeBitStream(self.img.readBytesAtOffset(self.rootDirBlock * self.blockSize, self.rootDirBlockCount * self.blockSize), NOE_BIGENDIAN)
			while len(self.flatRecords) < self.rootFileCount:
				if dirBs.checkEOF():
					break
				dirBlock = dirBs.tell() // self.blockSize
				nextBlock = (dirBs.tell() + 51) // self.blockSize
				if dirBlock != nextBlock: #wouldn't fit, align to next block
					dirBs.seek((dirBs.tell() + 511) & ~511, NOESEEK_ABS)
				record = MfsDirectoryRecord(self, dirBs)
				if record.isValid():
					self.flatRecords.append(record)				
		else:
			extData = self.loadFile(HfsFileId_Extents, self.extExtRec.ex, self.extFileSize)
			if len(extData) < self.extFileSize:
				#could try writing this blind, but really need an actual image sample to test it
				noesis.doException("No handling for extents overflow file overflowing.")
			extNodes = self.loadBTree(HfsTreeType_Extents, extData)
			for node in extNodes:
				for record in node.records:
					if record.extKey:
						forkType = record.extKey.forkType
						fileId = record.extKey.fileId
						extDict = self.extDict if forkType == HfsForkType_Data else self.resExtDict
						if fileId not in extDict:
							extDict[fileId] = []
						extDict[fileId].append(record)
			#now make sure each record list is sorted by first block
			for key in self.extDict.keys():
				self.extDict[key] = sorted(self.extDict[key], key=lambda a: a.extKey.firstAllocBlock)
			for key in self.resExtDict.keys():
				self.resExtDict[key] = sorted(self.resExtDict[key], key=lambda a: a.extKey.firstAllocBlock)

			catData = self.loadFile(HfsFileId_Catalog, self.catExtRec.ex, self.catFileSize, HfsForkFlags_Data | HfsForkFlags_Res)
			self.catNodes = self.loadBTree(HfsTreeType_Catalog, catData)

			#create a dictionary for directory records
			self.dirDict = {}
			for node in self.catNodes:
				if node.type == HfsNodeType_Leaf:
					for record in node.records:
						if record.catDataType == HfsCatDataType_DirRecord and record.catKey:
							self.dirDict[record.dirId] = record
	
	def loadFile(self, id, extents, size, forkFlags = HfsForkFlags_Data):
		data = bytearray()
		offsetsAndSizes = self.assembleFileOffsetsAndSizes(id, extents)
		img = self.img
		for partOffset, partSize in offsetsAndSizes:
			data += img.readBytesAtOffset(partOffset, partSize)			
		if len(data) > size:
			data = data[:size]
		return data
		
	def crawlBlockMapForOffsetsAndSizes(self, firstBlock, size):
		offsetsAndSizes = []
		readSize = 0
		currentBlock = firstBlock - 2
		baseOffset = self.firstAllocBlock * self.blockSize
		while readSize < size:
			offset = baseOffset + currentBlock * self.allocBlockSize
			readSize += self.allocBlockSize
			offsetsAndSizes.append((offset, self.allocBlockSize))
			currentBlock = self.blockMap[currentBlock] - 2
			if currentBlock < 0:
				break
		return offsetsAndSizes
		
	def assembleFileOffsetsAndSizes(self, id, extents, forkFlags = HfsForkFlags_Data):
		offsetsAndSizes = []
		img = self.img
		for startBlock, blockCount in extents:
			if blockCount > 0:
				offset = (self.firstAllocBlock + startBlock) * self.allocBlockSize
				exSize = blockCount * self.allocBlockSize
				offsetsAndSizes.append((offset, exSize))
				
		checkDicts = []
		if forkFlags & HfsForkFlags_Data:
			checkDicts.append(self.extDict)
		if forkFlags & HfsForkFlags_Res:
			checkDicts.append(self.resExtDict)
		
		for extDict in checkDicts:
			if id in extDict:
				extOverflows = extDict[id]
				for extOverflow in extOverflows:
					for startBlock, blockCount in extOverflow.ext.ex:
						if blockCount > 0:
							offset = (self.firstAllocBlock + startBlock) * self.allocBlockSize
							exSize = blockCount * self.allocBlockSize
							offsetsAndSizes.append((offset, exSize))

		return offsetsAndSizes
		
	def loadBTree(self, btType, btData):
		btBs = NoeBitStream(btData, NOE_BIGENDIAN)
		allNodesBm = bytearray()
		btRootNode = HfsNode(self, btType, 512, btBs)
		btNodes = []
		if btRootNode.type != HfsNodeType_Header:
			print("Error: Unexpected node type at start of btree type", btType)
		else:
			allNodesBm += btRootNode.nodeBitMap
			btNodes.append(btRootNode)
			nodeOffset = btRootNode.nodeSize
			for nodeIndex in range(1, btRootNode.nodeCount):
				nodeUsed = self.testBitmap(allNodesBm, nodeIndex)
				if nodeUsed:
					btBs.seek(nodeOffset, NOESEEK_ABS)
					node = HfsNode(self, btType, btRootNode.nodeSize, btBs)
					if node.nodeBitMap:
						allNodesBm += node.nodeBitMap
					btNodes.append(node)
				nodeOffset += btRootNode.nodeSize
		return btNodes

	def decodeString(self, data):
		return macEsperantoToAscii(data)
		
	#works for both blocks and nodes
	def testBitmap(self, bmData, blockIndex):
		return (bmData[blockIndex >> 3] & (0x80 >> (blockIndex & 7))) != 0

	def filterPath(self, path):
		return path.replace("\\", "_").replace("/", "_")
		
	def appendExtension(self, path, finderInfo):
		#see if we want to give it an extension
		if self.provideExtensions:
			finderType = finderInfo.fileType
			ext = macTypeToString(finderType)
			return path + "." + ext
		return path
		
	def createNoesisFiles(self):
		files = []
		for record in self.flatRecords:
			path = self.appendExtension(record.name, record.finderInfo)
			if record.lgResSize > 0:
				offsetsAndSizes = self.crawlBlockMapForOffsetsAndSizes(record.firstResBlock, record.lgResSize)
				lbas, sizes, offsets = self.img.convertOffsetsAndSizes(offsetsAndSizes, record.lgResSize)
				files.append(NoeImgFile("resfork/" + path, lbas, sizes, offsets))
			if record.lgDataSize > 0:
				offsetsAndSizes = self.crawlBlockMapForOffsetsAndSizes(record.firstDataBlock, record.lgDataSize)
				lbas, sizes, offsets = self.img.convertOffsetsAndSizes(offsetsAndSizes, record.lgDataSize)
				files.append(NoeImgFile(path, lbas, sizes, offsets))
		
		for node in self.catNodes:
			if node.type == HfsNodeType_Leaf:
				for record in node.records:
					if record.catDataType == HfsCatDataType_FileRecord and record.catKey:
						#first build the full path using the pre-built directory dict
						parentDirId = record.catKey.parentDirId
						parentDirs = []
						while parentDirId in self.dirDict:
							parentRecord = self.dirDict[parentDirId]
							parentDirs.append(self.filterPath(parentRecord.catKey.name))
							parentDirId = parentRecord.catKey.parentDirId
						path = ""
						for parentDirIndex in range(0, len(parentDirs)):
							parentDir = parentDirs[len(parentDirs) - parentDirIndex - 1]
							path += parentDir + "/"							
						path += self.filterPath(record.catKey.name)
						
						path = self.appendExtension(path, record.finderInfo)
							
						if record.lgResSize > 0:
							#put resource fork data under a different path
							resPath = "resfork/" + path
							offsetsAndSizes = self.assembleFileOffsetsAndSizes(record.fileId, record.resFork.ex, HfsForkFlags_Res)
							lbas, sizes, offsets = self.img.convertOffsetsAndSizes(offsetsAndSizes, record.lgResSize)
							files.append(NoeImgFile(resPath, lbas, sizes, offsets))
						
						if record.lgDataSize > 0:
							offsetsAndSizes = self.assembleFileOffsetsAndSizes(record.fileId, record.dataFork.ex, HfsForkFlags_Data)
							lbas, sizes, offsets = self.img.convertOffsetsAndSizes(offsetsAndSizes, record.lgDataSize)
							files.append(NoeImgFile(path, lbas, sizes, offsets))
				
		return files

class MfsDirectoryRecord:
	def __init__(self, mdb, bs):
		self.flags = bs.readUByte()
		if self.isValid():
			self.version = bs.readUByte()
			#this part's largely unchanged from hfs file record
			self.finderInfo = HfsFInfo(bs)
			self.fileId = bs.readUInt()
			self.firstDataBlock = bs.readUShort()
			self.lgDataSize = bs.readUInt()
			self.physDataSize = bs.readUInt()
			self.firstResBlock = bs.readUShort()
			self.lgResSize = bs.readUInt()
			self.physResSize = bs.readUInt()
			self.crDate = bs.readUInt()
			self.mdDate = bs.readUInt()
			nameSize = bs.readUByte()
			self.name = mdb.decodeString(bs.readBytes(nameSize))
	def isValid(self):
		return (self.flags & MfsRecordFlag_Valid) != 0

class HfsNode:
	def __init__(self, mdb, treeType, nodeSize, bs):
		self.nodeOffset = bs.tell()
		self.mdb = mdb
		self.fLink = bs.readUInt()
		self.bLink = bs.readUInt()
		self.type = bs.readUByte()
		self.height = bs.readByte()
		self.recordCount = bs.readUShort()
		bs.readUShort() #reserved
		bs.seek(self.nodeOffset + nodeSize - self.recordCount * 2)
		self.recordOffsets = [bs.readUShort() for x in range(0, self.recordCount)]
		self.records = []
		self.nodeBitMap = None
		if self.type == HfsNodeType_Header:
			if self.recordCount != 3:
				print("Warning: Expected header node to contain 3 records.")
			bs.seek(self.nodeOffset + self.recordOffsets[self.recordCount - 1], NOESEEK_ABS)
			self.depth = bs.readUShort()
			self.rootIndex = bs.readUInt()
			self.leafCount = bs.readUInt()
			self.fistLeafIndex = bs.readUInt()
			self.lastLeafIndex = bs.readUInt()
			self.nodeSize = bs.readUShort()
			self.maxKeySize = bs.readUShort()
			self.nodeCount = bs.readUInt()
			self.freeNodeCount = bs.readUInt()
			bs.seek(self.nodeOffset + self.recordOffsets[self.recordCount - 3], NOESEEK_ABS)
			self.nodeBitMap = bs.readBytes(256)
		elif self.type == HfsNodeType_Map:
			#probably should use the offset here, but haven't actually come across this case in the wild to test so this code is written blind
			bs.seek(self.nodeOffset + 0xE, NOESEEK_ABS)
			self.nodeBitMap = bs.readBytes(494)
		elif self.type == HfsNodeType_Index or self.type == HfsNodeType_Leaf:
			for recordIndex in range(0, self.recordCount):
				bs.seek(self.nodeOffset + self.recordOffsets[recordIndex], NOESEEK_ABS)
				record = HfsNodeRecord(self, treeType, mdb, bs)
				self.records.append(record)

class HfsNodeRecord:
	def __init__(self, node, treeType, mdb, bs):
		self.node = node
		self.catKey = self.extKey = None
		if node.type == HfsNodeType_Index:
			if treeType == HfsTreeType_Catalog:
				self.catKey = HfsCatKey(bs, mdb, node.type)
			#elif treeType == HfsTreeType_Extents:
			#	...
		elif node.type == HfsNodeType_Leaf:
			if treeType == HfsTreeType_Catalog:
				self.catKey = HfsCatKey(bs, mdb, node.type)
				self.catDataType = bs.readByte()
				bs.readByte() #reserved
				if self.catDataType == HfsCatDataType_DirRecord:
					self.flags = bs.readUShort()
					self.valence = bs.readUShort()
					self.dirId = bs.readUInt()
					self.crDate = bs.readUInt()
					self.mdDate = bs.readUInt()
					self.bkDate = bs.readUInt()
					self.finderInfo = HfsDInfo(bs)
					self.finderInfo2 = HfsDXInfo(bs)
					#reserved
					bs.readUInt()
					bs.readUInt()
					bs.readUInt()
					bs.readUInt()
				elif self.catDataType == HfsCatDataType_FileRecord:
					self.flags = bs.readUByte()
					self.type = bs.readUByte()
					self.finderInfo = HfsFInfo(bs)
					self.fileId = bs.readUInt()
					self.firstDataBlock = bs.readUShort()
					self.lgDataSize = bs.readUInt()
					self.physDataSize = bs.readUInt()
					self.firstResBlock = bs.readUShort()
					self.lgResSize = bs.readUInt()
					self.physResSize = bs.readUInt()
					self.crDate = bs.readUInt()
					self.mdDate = bs.readUInt()
					self.bkDate = bs.readUInt()
					self.finderInfo2 = HfsFXInfo(bs)
					self.clumpSize = bs.readUShort()
					self.dataFork = HfsExtDataRec(bs)
					self.resFork = HfsExtDataRec(bs)
					bs.readUInt() #reserved
				elif self.catDataType == HfsCatDataType_DirThreadRecord or self.catDataType == HfsCatDataType_FileThreadRecord:
					bs.readUInt() #reserved
					bs.readUInt() #reserved
					self.parentId = bs.readUInt()
					nameSize = bs.readUByte()
					self.name = mdb.decodeString(bs.readBytes(nameSize))
			elif treeType == HfsTreeType_Extents:
				self.extKey = HfsExtKey(bs, mdb, node.type)
				self.ext = HfsExtDataRec(bs)
	
class HfsCatKey:
	def __init__(self, bs, mdb, nodeType):
		self.keySize = bs.readByte()
		bs.readByte() #reserved
		self.parentDirId = bs.readUInt()
		strSize = bs.readUByte()
		self.name = mdb.decodeString(bs.readBytes(strSize))
		if not strSize & 1:
			bs.readUByte() #pad
		#would need to pad out if nodeType == HfsNodeType_Index, but since we're using the record offsets and nothing comes after this data for index nodes, we don't have to care			

class HfsExtKey:
	def __init__(self, bs, mdb, nodeType):
		self.keySize = bs.readByte()
		self.forkType = bs.readUByte()
		self.fileId = bs.readUInt()
		self.firstAllocBlock = bs.readUShort()

class HfsFInfo:
	def __init__(self, bs):
		self.fileType = bs.readUInt()
		self.fileCreator = bs.readUInt()
		self.flags = bs.readUShort()
		self.pV = bs.readUShort()
		self.pH = bs.readUShort()
		self.folder = bs.readUShort()

class HfsFXInfo:
	def __init__(self, bs):
		self.iconId = bs.readUShort()
		#reserved
		bs.readUShort()
		bs.readUShort()
		bs.readUShort()
		bs.readUShort()
		self.commentId = bs.readUShort()
		self.dirId = bs.readUInt()
		
class HfsDInfo:
	def __init__(self, bs):
		self.rTop = bs.readUShort()
		self.rLeft = bs.readUShort()
		self.rBottom = bs.readUShort()
		self.rRight = bs.readUShort()
		self.flags = bs.readUShort()
		self.pV = bs.readUShort()
		self.pH = bs.readUShort()
		self.view = bs.readUShort()

class HfsDXInfo:
	def __init__(self, bs):
		self.pV = bs.readUShort()
		self.pH = bs.readUShort()
		self.openChain = bs.readUInt()
		bs.readUShort() #reserved
		self.commentId = bs.readUShort()
		self.dirId = bs.readUInt()

class HfsExtDataRec:
	def __init__(self, bs):
		#startBlock, blockCount
		self.ex = [(bs.readUShort(), bs.readUShort()) for x in range(0, 3)]
		
class HfsForkData:
	def __init__(self, bs):
		self.logicalSize = bs.readUInt64()
		self.clumpSize = bs.readUInt()
		self.blockCount = bs.readUInt()
		#startBlock, blockCount
		self.ex = [(bs.readUInt(), bs.readUInt()) for x in range(0, 8)]

def macEsperantoToAscii(data):
	processedData = bytearray([x if x < 128 else ord(HfsEsperantoToAscii[x - 128]) for x in data])
	return processedData.decode("ascii")

def macTypeToString(finderType):
	typeBytes = noePack(">I", finderType).replace(b" ", b"_")
	#only allow letters, numbers, and a few special chars.
	specialChars = { ord(c) for c in "!@#$%%^&()_+-=,.[]{}" }
	if all((c >= 0x30 and c <= 0x39) or (c >= 0x41 and c <= 0x5A) or (c >= 0x61 and c <= 0x7A) or c in specialChars for c in typeBytes):
		return typeBytes.decode("ASCII")
	return "%08X"%finderType

class Iso9660VolumeDescriptor:
	def __init__(self, data):
		bs = NoeBitStream(data)
		self.type = bs.readUByte()
		self.id = bs.readBytes(5)
		self.version = bs.readUByte()
		if self.type == 0xFF:
			return
		bs.readUByte() #reserved
		self.sysId = noeAsciiFromBytes(bs.readBytes(32)).rstrip(" ")
		self.volId = noeAsciiFromBytes(bs.readBytes(32)).rstrip(" ")
		bs.readBytes(8) #reserved
		self.volSpace = bs.readUInt()
		bs.readUInt() #BE
		bs.readBytes(32) #reserved
		self.volSetSize = bs.readUInt()
		self.volSeqNum = bs.readUInt()
		self.blockSize = bs.readUShort()
		bs.readUShort() #BE
		self.pathTableSize = bs.readUInt()
		bs.readUInt() #BE
		self.pathTableLba = bs.readUInt()
		self.optionalPathTableLba = bs.readUInt()
		bs.readUInt() #BE
		bs.readUInt() #BE
		self.rootRecord = Iso9660Record(bs)
		self.volSetId = bs.readBytes(128)
		self.pubId = bs.readBytes(128)
		self.prepId = bs.readBytes(128)
		self.appId = bs.readBytes(128)
		self.copyrightId = bs.readBytes(37)
		self.abstractId = bs.readBytes(37)
		self.biblioId = bs.readBytes(37)
		self.createDate = Iso9660Date(bs)
		self.modDate = Iso9660Date(bs)
		self.expirDate = Iso9660Date(bs)
		self.effDate = Iso9660Date(bs)
		#currently discard the rest
		
	def sizeToSectorCount(self, size):
		return (size + (self.blockSize - 1)) // self.blockSize

Iso9660_DirFlag_Hidden = (1 << 0)
Iso9660_DirFlag_Directory = (1 << 1)
Iso9660_DirFlag_AssociatedFile = (1 << 2)
Iso9660_DirFlag_ExtendedAttr = (1 << 3)
Iso9660_DirFlag_Permissions = (1 << 4)
Iso9660_DirFlag_NotFinal = (1 << 7)
		
class Iso9660Record:
	def __init__(self, bs, parentRecord = None):
		ofs = bs.tell()
		self.recordSize = bs.readUByte()
		self.extendedSize = bs.readUByte()
		self.dataLba = bs.readUInt()
		bs.readUInt() #BE
		self.dataSize = bs.readUInt()
		bs.readUInt() #BE
		self.recDate = Iso9660Date()
		self.recDate.parseDirFormat(bs)
		self.flags = bs.readUByte() #Iso9660_DirFlag_*
		self.unitSize = bs.readUByte()
		self.gapSize = bs.readUByte()
		self.volSeqNum = bs.readUShort()
		bs.readUShort() #BE
		self.idLen = bs.readUByte()
		idData = bs.readBytes(self.idLen)
		self.id = noeAsciiFromBytes(idData)
		if self.idLen == 1 and idData[0] == 0:
			self.specialType = 1
		elif self.idLen == 1 and idData[0] == 1:
			self.specialType = 2
		else:
			self.specialType = 0
			si = self.id.rfind(";")
			if si >= 0:
				self.id = self.id[:si]
		#no need to read pad unless we actually want to parse extended data, since we're using the record size to skip ahead
		#if not (self.idLen & 1):
		#	bs.readUByte() #pad
		self.parentRecord = parentRecord
		bs.seek(ofs + self.recordSize, NOESEEK_ABS)
		
	def isSpecial(self):
		return self.specialType > 0
		
	def getFullPath(self):
		recs = [self]
		parent = self.parentRecord
		while parent:
			recs.append(parent)
			parent = parent.parentRecord
		path = ""
		for i in range(0, len(recs)):
			index = len(recs) - i - 1
			rec = recs[index]
			path += rec.id
			if index > 0 and len(path) > 0:
				path += "/"
		return path
		
class Iso9660PathTableEntry:
	def __init__(self, bs):
		self.idLen = bs.readUByte()
		self.extendedSize = bs.readUByte()
		self.recordLba = bs.readUInt()
		self.parentDirectoryIndex = bs.readUShort()
		self.id = noeAsciiFromBytes(bs.readBytes(self.idLen))
		if self.idLen & 1:
			bs.readUByte() #pad
		
class Iso9660Date:
	def __init__(self, bs = None):
		if bs:
			self.parseVDFormat(bs)
			
	def parseVDFormat(self, bs):
		self.year = int(noeAsciiFromBytes(bs.readBytes(4)))
		self.month = int(noeAsciiFromBytes(bs.readBytes(2)))
		self.day = int(noeAsciiFromBytes(bs.readBytes(2)))
		self.hour = int(noeAsciiFromBytes(bs.readBytes(2)))
		self.minute = int(noeAsciiFromBytes(bs.readBytes(2)))
		self.second = int(noeAsciiFromBytes(bs.readBytes(2)))
		self.centisecond = int(noeAsciiFromBytes(bs.readBytes(2)))
		self.gmtOffset = bs.readByte() #in 15 minute intervals, starting at interval -48 (west) and running up to interval 52 (east)
		
	def parseDirFormat(self, bs):
		self.year = 1900 + bs.readUByte()
		self.month = bs.readUByte()
		self.day = bs.readUByte()
		self.hour = bs.readUByte()
		self.minute = bs.readUByte()
		self.second = bs.readUByte()
		self.centisecond = 0
		self.gmtOffset = bs.readByte()
		
	def __repr__(self):
		return "%04i-%02i-%02i %02i:%02i:%02i.%i"%(self.year, self.month, self.day, self.hour, self.minute, self.second, self.centisecond)
