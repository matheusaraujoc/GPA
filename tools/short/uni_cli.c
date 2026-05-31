#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "unishox2.h"
int main(int argc,char**argv){
  if(argc<2)return 1;
  FILE*f=fopen(argv[1],"rb"); if(!f)return 1;
  fseek(f,0,SEEK_END); long n=ftell(f); fseek(f,0,SEEK_SET);
  char*in=malloc(n+1); if(fread(in,1,n,f)!=(size_t)n){return 1;} fclose(f);
  char*out=malloc(n*2+64); char*dec=malloc(n+64);
  int clen=unishox2_compress_simple(in,(int)n,out);
  int dlen=unishox2_decompress_simple(out,clen,dec);
  if(dlen!=(int)n||memcmp(dec,in,n)!=0){fprintf(stderr,"RTFAIL\n");return 2;}
  printf("%d\n",clen); return 0;
}
