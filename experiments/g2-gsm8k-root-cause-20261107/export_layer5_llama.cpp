#include "llama.h"
#include "ggml-backend.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>
#include <vector>
struct Cb { std::string out; int ntok; };
static int layer(const char*n){const char*p=strrchr(n,'-');return p?atoi(p+1):-1;}
static const char* stage(const char*n){
  if(strncmp(n,"l_out",5)==0)return "layer_output";
  if(strncmp(n,"attn_norm",9)==0)return "attn_normed_input";
  if(strncmp(n,"pe_in",5)==0)return "ple_residual_input";
  if(strncmp(n,"per_layer_embd_out",18)==0)return "ple_contribution";
  if(strncmp(n,"Qcur",4)==0 && strstr(n,"_normed")==nullptr && strstr(n,"_pos")==nullptr)return "q_proj";
  if(strncmp(n,"Kcur",4)==0 && strstr(n,"_normed")==nullptr && strstr(n,"_pos")==nullptr)return "k_proj";
  if(strncmp(n,"Vcur",4)==0 && strstr(n,"_normed")==nullptr)return "v_proj";
  if(strncmp(n,"Qcur_normed",11)==0)return "q_normed";
  if(strncmp(n,"Qcur_pos",8)==0)return "q_rope";
  if(strncmp(n,"Kcur_normed",11)==0)return "k_normed";
  if(strncmp(n,"Vcur_normed",11)==0)return "v_normed";
  if(strncmp(n,"Kcur_pos",8)==0)return "k_rope";
  if(strncmp(n,"attn_post_norm",14)==0)return "post_attention_normed";
  if(strncmp(n,"attn_out",8)==0)return "attn_residual";
  if(strncmp(n,"ffn_norm_1",10)==0)return "ffn_normed";
  if(strncmp(n,"ffn_mlp",7)==0)return "ffn_output";
  if(strncmp(n,"ffn_post_norm",13)==0)return "ffn_post_norm";
  if(strncmp(n,"ffn_out",7)==0)return "ffn_output";
  return nullptr;
}
static bool cb(ggml_tensor*t,bool ask,void*u){auto*c=(Cb*)u;const char*s=stage(t->name);if(!s||t->ne[1]!=c->ntok)return true;int il=layer(t->name);if(il!=5 && !(il==-1&&strcmp(s,"ple_contribution")==0))return true;if(ask)return true;if(t->type!=GGML_TYPE_F32)return true;std::vector<float>v(ggml_nelements(t));ggml_backend_tensor_get(t,v.data(),0,ggml_nbytes(t));std::vector<float>row(c->ntok*t->ne[0]);for(int j=0;j<t->ne[0];j++)for(int r=0;r<c->ntok;r++)row[r*t->ne[0]+j]=v[r*t->nb[1]/sizeof(float)+j*t->nb[0]/sizeof(float)];std::ofstream f(c->out+"."+s+".f32",std::ios::binary);f.write((char*)row.data(),row.size()*4);return true;}
int main(int ac,char**av){if(ac!=5)return 2;int n=atoi(av[3]);std::ifstream f(av[2],std::ios::binary);std::vector<llama_token>tok(n);f.read((char*)tok.data(),n*4);if(!f||f.peek()!=EOF)return 3;auto mp=llama_model_default_params();mp.n_gpu_layers=0;auto*m=llama_model_load_from_file(av[1],mp);if(!m)return 4;auto cp=llama_context_default_params();cp.n_ctx=8192;cp.n_batch=2048;cp.n_ubatch=2048;cp.n_threads=24;cp.n_threads_batch=24;Cb c{av[4],n};cp.cb_eval=cb;cp.cb_eval_user_data=&c;auto*ctx=llama_init_from_model(m,cp);if(!ctx)return 5;auto b=llama_batch_init(n,0,1);b.n_tokens=n;for(int i=0;i<n;i++){b.token[i]=tok[i];b.pos[i]=i;b.n_seq_id[i]=1;b.seq_id[i][0]=0;b.logits[i]=(i==n-1);}int ret=llama_decode(ctx,b);llama_batch_free(b);llama_free(ctx);llama_model_free(m);return ret;}
