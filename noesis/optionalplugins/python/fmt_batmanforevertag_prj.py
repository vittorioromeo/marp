from inc_noesis import *
import os

def registerNoesisTypes():
	handle = noesis.register("Batman Forever TAG PRJ", ".prj")
	noesis.setHandlerTypeCheck(handle, prjCheckType)
	noesis.setHandlerLoadRGBA(handle, prjLoadRGBA)
	return 1

def prjCheckType(data):
	try:
		lines = data.decode("ASCII").splitlines()
		if len(lines) <= 3:
			return 0
		maxCheckLines = 6
		for i in range(0, min(len(lines), maxCheckLines)):
			s = lines[i].split(":", 1)
			if len(s) > 1 and s[0] == "MultiFile":
				return 1
	except:
		pass
	return 0
	
class PrjFrame:
	def __init__(self, params):
		self.frameIndex = int(params["F"])
		self.width = int(params["W"])
		self.height = int(params["H"])
		self.x = int(params["X"])
		self.y = int(params["Y"])
		self.ox = -int(params["OX"])
		self.oy = -int(params["OY"])
		self.name = params["NAME"]
		
	def getMinMax(self):
		return self.ox, self.oy, self.ox + self.width, self.oy + self.height

def prjFrameBounds(frames):
	minX, minY, maxX, maxY = frames[0].getMinMax()
	for i in range(1, len(frames)):
		fminX, fminY, fmaxX, fmaxY = frames[i].getMinMax()
		minX = min(minX, fminX)
		minY = min(minY, fminY)
		maxX = max(maxX, fmaxX)
		maxY = max(maxY, fmaxY)
	return minX, minY, maxX, maxY

def prjLoadRGBA(data, texList):
	rapi.processCommands("-flctindex 0 -flctindex 1 -flctindex 2")

	lines = data.decode("ASCII").splitlines()
	flcTextures = None
	frames = []
	for line in lines:
		s = line.split(":", 1)
		if len(s) > 1:
			if s[0] == "MultiFile":
				dirPath, localPath = os.path.split(s[1])
				fullPath = os.path.join(rapi.getDirForFilePath(rapi.getLastCheckedName()), localPath)
				if not os.path.exists(fullPath):
					print("Error: MultiFile not found:", fullPath)
				else:
					with open(fullPath, "rb") as f:
						flcTextures = rapi.loadTexByHandler(f.read(), ".flc", 1)
						if not flcTextures:
							print("Error: Failed to load MultiFile:", fullPath)
			elif s[0] == "MultiData":
				if not flcTextures:
					print("Warning: MultiData without MultiFile loaded.")
				else:
					params = dict(entry.split("=") for entry in s[1].lstrip(" ").split(" "))
					frame = PrjFrame(params)
					if frame.frameIndex < 0 or frame.frameIndex >= len(flcTextures):
						print("Warning: Frame index out of range:", frameIndex, len(flcTextures))
					else:
						frames.append(frame)
						
	if len(frames) == 0:
		return 0

	minX, minY, maxX, maxY = prjFrameBounds(frames)
	canvasWidth = maxX - minX
	canvasHeight = maxY - minY
		
	textures = []
	for frame in frames:
		srcTex = flcTextures[frame.frameIndex]
		srcRgba = rapi.imageGetTexRGBA(srcTex)
		canvasRgba = bytearray(canvasWidth * canvasHeight * 4)	
		fminX, fminY, fmaxX, fmaxY = frame.getMinMax()		
		rapi.imageBlit32(canvasRgba, canvasWidth, canvasHeight, fminX - minX, fminY - minY, srcRgba, frame.width, frame.height, frame.x, frame.y, canvasWidth * 4, srcTex.width * 4, noesis.BLITFLAG_ALPHABLEND)
		tex = NoeTexture(frame.name, canvasWidth, canvasHeight, canvasRgba, noesis.NOESISTEX_RGBA32)
		texList.append(tex)
	
	return 1

