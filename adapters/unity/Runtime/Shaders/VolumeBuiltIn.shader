Shader "Vapor/VolumeBuiltIn"
{
 Properties{_Atlas("Density atlas",2D)="black"{} _FloatField("Float32 density / temperature",3D)=""{} _DensityCap("Density cap",Float)=8 _Extinction("Extinction",Float)=16 _Steps("Steps",Range(8,256))=96 _Colour("Colour",Color)=(.85,.9,.95,1) _Anisotropy("Anisotropy",Range(-.9,.9))=0 _Albedo("Albedo",Range(0,1))=1 _Emission("Emission",Float)=0 _ThermalFade("Thermal opacity",Range(0,1))=0 _Ambient("Ambient",Range(0,1))=.3}
 SubShader{Tags{"Queue"="Transparent" "RenderType"="Transparent"}Cull Front ZWrite Off ZTest Always Blend One OneMinusSrcAlpha
 Pass{
 CGPROGRAM
 #pragma vertex vert
 #pragma fragment frag
 #pragma target 3.5
 #pragma multi_compile_local _ VAPOR_FLOAT_FIELD
 #include "UnityCG.cginc"
 #include "VaporRaymarch.hlsl"
 UNITY_DECLARE_DEPTH_TEXTURE(_CameraDepthTexture);
 struct appdata{float4 vertex:POSITION;};
 struct v2f{float4 pos:SV_POSITION;float3 local:TEXCOORD0;float4 screen:TEXCOORD1;float3 world:TEXCOORD2;};
 v2f vert(appdata v){v2f o;o.pos=UnityObjectToClipPos(v.vertex);o.local=v.vertex.xyz+.5;o.screen=ComputeScreenPos(o.pos);o.world=mul(unity_ObjectToWorld,v.vertex).xyz;return o;}
 float4 frag(v2f i):SV_Target{
  float3 ro=mul(unity_WorldToObject,float4(_WorldSpaceCameraPos,1)).xyz+.5;
  float depth=SAMPLE_DEPTH_TEXTURE_PROJ(_CameraDepthTexture,UNITY_PROJ_COORD(i.screen));float eyeDepth=LinearEyeDepth(depth);
  float3 worldRay=normalize(i.world-_WorldSpaceCameraPos);float along=max(dot(worldRay,-UNITY_MATRIX_V[2].xyz),1e-5);
  return VaporMarch(ro,i.local,eyeDepth/along);
 }
 ENDCG
 }}
}
