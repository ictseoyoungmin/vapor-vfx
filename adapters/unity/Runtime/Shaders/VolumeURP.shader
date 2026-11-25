Shader "Vapor/VolumeURP"
{
 Properties{_Atlas("Density atlas",2D)="black"{} _FloatField("Float32 density / temperature",3D)=""{} _DensityCap("Density cap",Float)=8 _Extinction("Extinction",Float)=16 _Steps("Steps",Range(8,256))=96 _Colour("Colour",Color)=(.85,.9,.95,1) _Anisotropy("Anisotropy",Range(-.9,.9))=0 _Albedo("Albedo",Range(0,1))=1 _Emission("Emission",Float)=0 _ThermalFade("Thermal opacity",Range(0,1))=0 _Ambient("Ambient",Range(0,1))=.3}
 SubShader{Tags{"RenderPipeline"="UniversalPipeline" "Queue"="Transparent" "RenderType"="Transparent"}Cull Front ZWrite Off ZTest Always Blend One OneMinusSrcAlpha
 Pass{Tags{"LightMode"="UniversalForward"}
 HLSLPROGRAM
 #pragma vertex vert
 #pragma fragment frag
 #pragma target 3.5
 #pragma multi_compile_local _ VAPOR_FLOAT_FIELD
 #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
 #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/DeclareDepthTexture.hlsl"
 #include "VaporRaymarch.hlsl"
 struct Attributes{float4 positionOS:POSITION;};
 struct Varyings{float4 positionCS:SV_POSITION;float3 local:TEXCOORD0;float3 world:TEXCOORD1;};
 Varyings vert(Attributes input){Varyings o;o.positionCS=TransformObjectToHClip(input.positionOS.xyz);o.local=input.positionOS.xyz+.5;o.world=TransformObjectToWorld(input.positionOS.xyz);return o;}
 float4 frag(Varyings i):SV_Target{
  float3 ro=TransformWorldToObject(GetCameraPositionWS())+.5;float2 uv=GetNormalizedScreenSpaceUV(i.positionCS);float depth=SampleSceneDepth(uv);
  float eyeDepth=LinearEyeDepth(depth,_ZBufferParams);float3 worldRay=normalize(i.world-GetCameraPositionWS());float along=max(dot(worldRay,-UNITY_MATRIX_V[2].xyz),1e-5);
  return VaporMarch(ro,i.local,eyeDepth/along);
 }
 ENDHLSL
 }}
}
