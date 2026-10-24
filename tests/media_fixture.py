"""Small synthetic MJPEG AVI; contains no downloaded or personal media."""
import struct
from PySide6.QtCore import QBuffer,QByteArray,QIODevice
from PySide6.QtGui import QImage,QColor

def make_video(path):
    frames=[]
    for index in range(12):
        image=QImage(160,120,QImage.Format.Format_RGB32);image.fill(QColor.fromHsv(index*30,160,200))
        content=QByteArray();buffer=QBuffer(content);buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        assert image.save(buffer,'JPEG');buffer.close();frames.append(bytes(content))
    def chunk(kind,data):return kind+struct.pack('<I',len(data))+data+(b'\0' if len(data)%2 else b'')
    def group(kind,data):return chunk(b'LIST',kind+data)
    size=max(map(len,frames))
    avih=struct.pack('<14I',166667,size*6,0,0x10,12,0,1,size,160,120,0,0,0,0)
    strh=struct.pack('<4s4sIHH8I4h',b'vids',b'MJPG',0,0,0,0,1,6,0,12,size,0xffffffff,0,0,0,160,120)
    strf=struct.pack('<IiiHH4sIiiII',40,160,120,1,24,b'MJPG',160*120*3,0,0,0,0)
    header=group(b'hdrl',chunk(b'avih',avih)+group(b'strl',chunk(b'strh',strh)+chunk(b'strf',strf)))
    movie=b'';index=b''
    for frame in frames:
        index+=struct.pack('<4sIII',b'00dc',0x10,4+len(movie),len(frame));movie+=chunk(b'00dc',frame)
    data=b'AVI '+header+group(b'movi',movie)+chunk(b'idx1',index)
    path.write_bytes(b'RIFF'+struct.pack('<I',len(data))+data)
    return path
