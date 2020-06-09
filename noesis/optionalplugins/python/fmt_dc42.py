from inc_noesis import *
from inc_imgtools import NoeImgReader, NoeImgTrack, NoeImg_TrackType_Data, HfsVersion_Hfs

HFS_SECTOR_SIZE = 512 #feel free to adjust as needed
DC42_DATA_OFFSET = 0x54
ENABLE_HFS_DUMPER = False #warning, does not validate hfs contents and will semi-blindly attempt to restore mdb if it's missing

def registerNoesisTypes():
	handle = noesis.register("DC42 container", ".dc42")
	noesis.setHandlerExtractArc(handle, dc42ExtractArc)
	#support raw images too
	handle = noesis.register("HFS container", ".hfs")
	noesis.setHandlerExtractArc(handle, hfsExtractArc)
	
	if ENABLE_HFS_DUMPER:
		toolHandle = noesis.registerTool("HFS Dumper", hfsDumpToolMethod, "Scans current directory for dc42 images to dump hfs files.")
	return 1

def genericHfsExtract(track, justChecking):
	img = NoeImgReader([track])
	r = 0
	if img.containsHFS():
		if not justChecking:
			imgVol = img.readHFS()
			if imgVol:
				for imgFile in imgVol.files:
					writePath = imgFile.path
					print("Writing", writePath)
					rapi.exportArchiveFile(writePath, img.readFileData(imgFile))
		r = 1
	img.close()
	return r

def dc42Validate(bs, f, fileLen):
	bs.seek(0x50)
	diskEnc = bs.readUByte()
	diskFormat = bs.readUByte()
	if bs.readUShort() != 0x100:
		return 0, 0, 0
	bs.seek(0x40)
	dataSize = bs.readUInt()
	tagSize = bs.readUInt()
	totalSize = DC42_DATA_OFFSET + dataSize + tagSize
	if totalSize > fileLen or dataSize == 0:
		return 0, 0, 0
	interleaveFormat = diskFormat & 31

	#possible todo - may need handling for different sector ordering, but don't have any data to test with
	track = NoeImgTrack(f, 0, 0, HFS_SECTOR_SIZE, HFS_SECTOR_SIZE, 0, NoeImg_TrackType_Data, False, 0x54)

	return dataSize, interleaveFormat, track
			
def dc42ExtractArc(fileName, fileLen, justChecking):
	if fileLen <= DC42_DATA_OFFSET:
		return 0

	r = 0
	with open(fileName, "rb") as f:
		bs = NoeFileStream(f, NOE_BIGENDIAN)
		dataSize, interleaveFormat, track = dc42Validate(bs, f, fileLen)
		if dataSize <= 0:
			return 0
			
		r = genericHfsExtract(track, justChecking)

	return r

def hfsExtractArc(fileName, fileLen, justChecking):
	track = NoeImgTrack(open(fileName, "rb"), 0, 0, HFS_SECTOR_SIZE, HFS_SECTOR_SIZE, 0)
	return genericHfsExtract(track, justChecking)

def hfsDumpToolMethod(toolIndex):
	noesis.logPopup()	
	baseDir = noesis.userPrompt(noesis.NOEUSERVAL_FOLDERPATH, "Open Folder", "Select a folder to scan.", noesis.getSelectedDirectory(), None)
	if not baseDir:
		return 0
	
	for root, dirs, files in os.walk(baseDir):
		for localPath in files:
			if localPath.lower().endswith(".dc42"):
				fullPath = os.path.join(root, localPath)
				with open(fullPath, "rb") as f:
					f.seek(0, os.SEEK_END)
					fileLen = f.tell()
					f.seek(0, os.SEEK_SET)
					bs = NoeFileStream(f, NOE_BIGENDIAN)
					dataSize, interleaveFormat, track = dc42Validate(bs, f, fileLen)
					if dataSize > 0:
						localPath, ext = os.path.splitext(fullPath)
						dstPath = localPath + ".hfs"
						print("Writing:", dstPath)
						with open(dstPath, "wb") as fw:
							f.seek(DC42_DATA_OFFSET, os.SEEK_SET)
							#don't bother chunking since we expect these to be small
							fw.write(f.read(dataSize))
							if not genericHfsExtract(track, True):
								#if there's no hfs mdb, see if we've got one on the end
								f.seek(DC42_DATA_OFFSET + dataSize - 1024)
								id = noeUnpack(">H", f.read(2))[0]
								if id == HfsVersion_Hfs: #found one, transplant it
									f.seek(-2, os.SEEK_CUR)
									fw.seek(1024, os.SEEK_SET)
									fw.write(f.read(512))
		break
	
	return 0
