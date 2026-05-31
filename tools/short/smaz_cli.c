#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "smaz.h"
int main(int argc,char**argv){
  if(argc<2)return 1;
  FILE*f=fopen(argv[1],"rb"); if(!f)return 1;
  fseek(f,0,SEEK_END); long n=ftell(f); fseek(f,0,SEEK_SET);
  char*in=malloc(n+1); if(fread(in,1,n,f)!=(size_t)n){return 1;} fclose(f);
  int cap=n*2+512; char*out=malloc(cap);
  int clen=smaz_compress(in,(int)n,out,cap);
  printf("%d\n",clen); return 0;
}
