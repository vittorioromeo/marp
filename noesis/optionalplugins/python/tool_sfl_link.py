#originally written to link object files included in the source distribution of an unreleased snes tarzan game.
#those object files were produced by the "sasm32" 65C816 assembler.
from inc_noesis import *
import os

#set to true if object files don't already contain a snes header
WRITE_SNES_HEADER = True
SNES_MAKEUP = 0x31 #fastrom, hirom
SNES_TYPE = 0
SNES_ROM_SIZE = 0xC #4MB
SNES_SRAM_SIZE = 0x4 #16KB

#tarzan hack
TARZAN_CONTROL_FIX = False

def registerNoesisTypes():
	handle = noesis.registerTool("SFL Object Linker", sflLinkToolMethod, "Perform SFL object link.")
	return 1

class NobHeader:
	def __init__(self, f):
		try:
			id, addr, size, bank = noeUnpack("<IHHI", f.read(12))
			self.id = id
			self.addr = addr
			self.size = size
			self.bank = bank
		except:
			self.id = 0
			
	def isValid(self):
		return self.id == 0x01424F4E
		
	def getAbsAddr(self):
		return self.addr | (self.bank << 16)
	
def sflLoadObjectParts(objFiles):
	objectParts = []
	for objFile in objFiles:
		print("Parsing", objFile)
		with open(objFile, "rb") as f:
			nob = NobHeader(f)
			if not nob.isValid():
				print("Warning: Unexpected object file header.")
			else:
				while nob.isValid():
					data = f.read(nob.size)
					if nob.bank > 0xFFFF:
						print("Warning: Unexpected bank range:", nob.bank)
					objectParts.append((nob, data))
					nob = NobHeader(f)
	return objectParts

def sflLinkToolMethod(toolIndex):
	noesis.logPopup()

	baseDir = noesis.userPrompt(noesis.NOEUSERVAL_FOLDERPATH, "Open Folder", "Select a folder to scan for objects.", noesis.getSelectedDirectory(), None)
	if not baseDir:
		return 0

	objFiles = []
	for root, dirs, files in os.walk(baseDir):
		for localPath in files:
			if localPath.lower().endswith(".o"):
				fullPath = os.path.join(root, localPath)
				objFiles.append(fullPath)
		break
		
	print("Found", len(objFiles), "object files.")
	if len(objFiles) == 0:
		return 0

	objectParts = sflLoadObjectParts(objFiles)
					
	print("Loaded", len(objectParts), "object parts.")
	if len(objectParts) == 0:
		return 0
		
	#alright, slam them into a binary
	dstPath = noesis.userPrompt(noesis.NOEUSERVAL_SAVEFILEPATH, "Save File", "Select destination for binary.", os.path.join(noesis.getSelectedDirectory(), "_compiled_.bin"), None)
	if not dstPath:
		return 0

	with open(dstPath, "wb") as fw:
		for nob, data in objectParts:
			fw.seek(nob.getAbsAddr(), os.SEEK_SET)
			fw.write(data)
		if WRITE_SNES_HEADER:
			fw.seek(0, os.SEEK_END)
			totalSize = fw.tell()
			expectedSize = 1024 << SNES_ROM_SIZE
			if totalSize > expectedSize:
				print("Warning: Binary is larger than expected size:", totalSize, "vs", expectedSize)
			elif totalSize < expectedSize:
				#pad it out
				fw.write(bytearray(expectedSize - totalSize))
			fw.seek(0xFFC0, os.SEEK_SET)
			fw.write("NOESIS GENERATED ROM ".encode("ASCII"))
			fw.write(noePack("BBBB", SNES_MAKEUP, SNES_TYPE, SNES_ROM_SIZE, SNES_SRAM_SIZE))
		if TARZAN_CONTROL_FIX:
			#patch ScanjoysOpt to jmp directly to Scanjoys
			fw.seek(0x1C853, os.SEEK_SET)
			fw.write(noePack("BBBB", 0x5C, 0x6C, 0xA2, 0x80))

		print("Wrote", dstPath)
		
	return 0
	