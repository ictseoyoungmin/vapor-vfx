// Shared Built-in / URP implementation. Uses premultiplied output.
sampler2D _Atlas;
sampler3D _FloatField;
float4 _Grid,_Extent,_Colour;
float _DensityCap,_Extinction,_Steps,_Anisotropy,_Albedo,_Emission,_ThermalFade,_Ambient;
float2 VaporField(float3 uv)
{
    uv.z=1.0-uv.z; // Unity left-handed local positive box -> Rust right-handed volume.
    if(any(uv<0.0)||any(uv>1.0))return 0;
    #if defined(VAPOR_FLOAT_FIELD)
    // VPF1 stores physical density and temperature, not normalized atlas values.
    float2 f=tex3Dlod(_FloatField,float4(uv,0)).rg;
    return float2(f.r/max(_DensityCap,1e-6),f.g/16.0);
#else
    float3 p=clamp(uv*_Grid.xyz,0.5,_Grid.xyz-0.5);
    float z=p.z-.5,z0=floor(z),z1=min(z0+1,_Grid.z-1);
    float2 a=float2(p.x/_Grid.x,(z0*_Grid.y+p.y)/(_Grid.y*_Grid.z));
    float2 b=float2(a.x,(z1*_Grid.y+p.y)/(_Grid.y*_Grid.z));
    return lerp(tex2Dlod(_Atlas,float4(a,0,0)).rg,tex2Dlod(_Atlas,float4(b,0,0)).rg,frac(z));
#endif
}
float VaporDensity(float3 p){float2 f=VaporField(p);return f.r*_DensityCap*(1-_ThermalFade*(1-exp(-f.g*16)));}
bool VaporHit(float3 ro,float3 rd,out float nearT,out float farT)
{
    nearT=0;farT=1e8;
    [unroll]for(int a=0;a<3;a++){
        if(abs(rd[a])<1e-7){if(ro[a]<0||ro[a]>1)return false;}
        else{float t0=-ro[a]/rd[a],t1=(1-ro[a])/rd[a];nearT=max(nearT,min(t0,t1));farT=min(farT,max(t0,t1));}
    }
    return farT>nearT;
}
float4 VaporMarch(float3 ro,float3 point,float sceneDistance)
{
    float3 rd=normalize(point-ro);float a,b;if(!VaporHit(ro,rd,a,b))return 0;
    float metric=length(rd*_Extent.xyz);b=min(b,sceneDistance/max(metric,1e-6));if(b<=a)return 0;
    int steps=(int)clamp(_Steps,8,256);float dt=(b-a)/steps;float alpha=0;float3 colour=0;float3 lightDir=normalize(float3(-.45,.8,.35));float shadowStep=min(_Extent.x,min(_Extent.y,_Extent.z))/8;float g=clamp(_Anisotropy,-.9,.9);float phase=min(4.,(1-g*g)/pow(max(.001,1+g*g-2*g*dot(normalize(rd*_Extent.xyz),lightDir)),1.5));
    [loop]for(int i=0;i<256;i++){
        if(i>=steps||alpha>.995)break;float3 p=ro+rd*(a+(i+.5)*dt);float d=VaporDensity(p);
        #if defined(VAPOR_FLOAT_FIELD)
        if(d<=0.0)continue;
        #else
        if(d<.001)continue;
        #endif
        float shadow=1;
        [unroll]for(int j=1;j<=8;j++)shadow*=exp(-VaporDensity(p+lightDir*(j*shadowStep)/_Extent.xyz)*_Extinction*shadowStep);
        float opacity=1-exp(-d*_Extinction*dt*metric);float w=(1-alpha)*opacity;float heat=saturate(VaporField(p).g*16/5);colour+=w*(_Colour.rgb*_Albedo*(_Ambient+(1-_Ambient)*shadow*phase)+float3(1,.3,.045)*_Emission*heat*heat);alpha+=w;
    }
    return float4(colour,alpha);
}
