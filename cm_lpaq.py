import math, subprocess, os, tempfile, zlib, brotli
import zstandard as zst
BASE=r"c:\Users\Matheus\Documents\Projetos\GPA"; EXE=os.path.join(BASE,"main_test.exe"); W=tempfile.mkdtemp()
def squash(x):
    if x>20:return 0.999999
    if x<-20:return 1e-6
    return 1/(1+math.exp(-x))
def stretch(p): return math.log(p/(1-p))
LN2=math.log(2)
# contextos: (nome, order, table_bits). order 0 = so c0
CTX=[('o0',0,8),('o1',1,16),('o2',2,18),('o3',3,18),('o4',4,18),('o6',6,18),('wd',-1,18)]
def isalnum(b): return (48<=b<=57) or (65<=b<=90) or (97<=b<=122)

def cm_ideal(data, params):
    LR=params['LR']; APMR=params['APMR']; MSTR=params['MSTR']; CAP=params['CAP']; MINM=params['MINM']
    masks=[(1<<tb)-1 for _,_,tb in CTX]
    P=[[0.5]*(1<<tb) for _,_,tb in CTX]; C=[[0]*(1<<tb) for _,_,tb in CTX]
    NM=len(CTX)+1  # contextos + match
    nmix=256; w=[[0.2]*NM for _ in range(nmix)]
    NSEG=32; apm=[[squash((s/NSEG*16)-8) for s in range(NSEG+1)] for _ in range(256)]
    mm={}; mptr=-1; mlen=0
    n=len(data); bits=0.0; wordh=0
    for pos in range(n):
        byte=data[pos]
        # hashes base por contexto
        bh=[]
        for (name,order,tb) in CTX:
            if order==0: bh.append(0)
            elif order<0:
                bh.append(wordh)  # contexto de palavra
            else:
                h=0
                for k in range(max(0,pos-order),pos): h=(h*0x9E3779B1+data[k]+1)&0xFFFFFFFF
                bh.append(h)
        pb=data[mptr] if (mlen>0 and 0<=mptr<pos) else None
        prevb=data[pos-1] if pos>0 else 0
        c0=1
        for bp in range(8):
            bit=(byte>>(7-bp))&1; inp=[]; cells=[]
            for idx,((name,order,tb),mask,h) in enumerate(zip(CTX,masks,bh)):
                ci=((h*257)^(c0*0x6789DBB5))&mask; cells.append(ci)
                inp.append(stretch(min(max(P[idx][ci],1e-6),1-1e-6)))
            if pb is not None:
                pbit=(pb>>(7-bp))&1; s=min(mlen,28)*MSTR; inp.append(s if pbit else -s)
            else: inp.append(0.0)
            sel=c0&255
            z=sum(w[sel][i]*inp[i] for i in range(NM)); pm=min(max(squash(z),1e-6),1-1e-6)
            # APM
            actx=prevb
            x=(stretch(pm)+8)/16*NSEG; x=min(max(x,0),NSEG-1e-6); lo=int(x); wt=x-lo
            pa=apm[actx][lo]*(1-wt)+apm[actx][lo+1]*wt; pa=min(max(pa,1e-6),1-1e-6)
            p=(pm+3*pa)/4; p=min(max(p,1e-6),1-1e-6)
            bits+= -(math.log(p if bit else 1-p))/LN2
            err=bit-pm
            for i in range(NM): w[sel][i]+=LR*err*inp[i]
            for idx,ci in enumerate(cells):
                c=C[idx][ci]; rate=1.0/(c+1.5) if c<CAP else 1.0/(CAP+1.5)
                P[idx][ci]+=(bit-P[idx][ci])*rate; C[idx][ci]=c+1
            apm[actx][lo]+=(bit-apm[actx][lo])*APMR; apm[actx][lo+1]+=(bit-apm[actx][lo+1])*APMR
            c0=(c0<<1)|bit
        # match model update
        if pb is not None and pb==byte: mlen+=1; mptr+=1
        else: mlen=0; mptr=-1
        if pos>=MINM-1:
            h=0
            for k in range(pos-MINM+1,pos+1): h=(h*0x9E3779B1+data[k]+1)&0xFFFFFFFF
            if mlen==0:
                pv=mm.get(h,-1)
                if pv>=0: mptr=pv; mlen=1
            mm[h]=pos+1
        # word hash
        if isalnum(byte): wordh=(wordh*0x9E3779B1+byte+1)&0xFFFFFFFF
        else: wordh=0
    return bits/8

def gpa(d):
    i=os.path.join(W,"i");o=os.path.join(W,"o");open(i,"wb").write(d);subprocess.run([EXE,"c",i,o],capture_output=True);return os.path.getsize(o)
def gz(d): return len(zlib.compress(d,9))
zc=zst.ZstdCompressor(level=19)
def rd(p,n=None):
    d=open(os.path.join(BASE,p),"rb").read(); return d[:n] if n else d
files={'app.py 9.9KB':rd('app.py'),'ghost_core 16KB':rd('ghost_core.rs',16384),'spec.md 24KB':rd('spec.md')}
params=dict(LR=0.008,APMR=0.02,MSTR=0.5,CAP=60,MINM=6)
def pct(c,o): return f"{(1-c/o)*100:.1f}%"
print(f"params: {params}")
print(f"{'arquivo':<16}{'orig':>7}{'CM-lpaq':>9}{'GPA-frio':>9}{'gzip9':>7}{'zstd19':>8}{'brotli':>8}")
for n,d in files.items():
    o=len(d); cm=cm_ideal(d,params); g=gpa(d); z=len(zc.compress(d)); b=len(brotli.compress(d,quality=11))
    print(f"{n:<16}{o:>7}{pct(cm,o):>9}{pct(g,o):>9}{pct(gz(d),o):>7}{pct(z,o):>8}{pct(b,o):>8}")
