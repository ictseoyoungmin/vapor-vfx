using System;
using UnityEngine;
using UnityEngine.Rendering;
namespace VaporGame.Unity {
    /// <summary>Static VPF1 scalar asset. Uses the existing Unity volume optics,
    /// not exact parity with the reference Fidelity renderer. No fluid runtime required.</summary>
    [DisallowMultipleComponent]
    public sealed class VaporBakedVolume:MonoBehaviour {
        public TextAsset fieldAsset; // Import the .vpf as .bytes in Unity.
        public Shader volumeShader;
        public Color colour=new Color(.96f,.97f,1);
        [Min(0)]public float extinction=.32f;
        [Range(-.9f,.9f)]public float anisotropy=.58f;
        [Range(0,1)]public float albedo=.95f,ambient=.1f;
        [Range(8,256)]public int steps=128;
        Texture3D field;Material material;GameObject proxy;
        void OnEnable(){try{
            if(!fieldAsset)throw new ArgumentException("Assign a VPF1 .bytes TextAsset");
            if((transform.lossyScale-Vector3.one).sqrMagnitude>1e-6f)throw new InvalidOperationException("Unit-scale root required");
            var a=FieldAsset.Decode(fieldAsset.bytes);var g=a.Fields.Grid;
            if(!SystemInfo.supports3DTextures||!SystemInfo.SupportsTextureFormat(TextureFormat.RGFloat)||Math.Max(g.Nx,Math.Max(g.Ny,g.Nz))>(uint)SystemInfo.maxTexture3DSize)throw new InvalidOperationException("RGFloat 3D texture unavailable; no silent 8-bit fallback");
            int n=a.Fields.Density.Length;var packed=new float[checked(n*2)];for(int i=0;i<n;i++){packed[2*i]=a.Fields.Density[i];packed[2*i+1]=a.Fields.Temperature[i];}
            field=new Texture3D((int)g.Nx,(int)g.Ny,(int)g.Nz,TextureFormat.RGFloat,false){wrapMode=TextureWrapMode.Clamp,filterMode=FilterMode.Trilinear};field.SetPixelData(packed,0);field.Apply(false,true);
            if(!volumeShader)volumeShader=Shader.Find(GraphicsSettings.currentRenderPipeline?"Vapor/VolumeURP":"Vapor/VolumeBuiltIn");if(!volumeShader||!volumeShader.isSupported)throw new InvalidOperationException("Assign a supported Vapor shader");
            material=new Material(volumeShader);material.EnableKeyword("VAPOR_FLOAT_FIELD");material.SetTexture("_FloatField",field);material.SetVector("_Grid",new Vector4(g.Nx,g.Ny,g.Nz,0));var extent=new Vector3((float)g.Extent.X,(float)g.Extent.Y,(float)g.Extent.Z);material.SetVector("_Extent",extent);material.SetFloat("_DensityCap",(float)g.DensityCap);material.SetColor("_Colour",colour);material.SetFloat("_Extinction",extinction);material.SetFloat("_Anisotropy",anisotropy);material.SetFloat("_Albedo",albedo);material.SetFloat("_Ambient",ambient);material.SetFloat("_Steps",steps);material.SetFloat("_Emission",0);material.SetFloat("_ThermalFade",0);
            proxy=GameObject.CreatePrimitive(PrimitiveType.Cube);proxy.name="Vapor Baked Float32";proxy.layer=gameObject.layer;proxy.transform.SetParent(transform,false);proxy.transform.localScale=extent;proxy.transform.localPosition=extent*.5f;var col=proxy.GetComponent<Collider>();if(col)Destroy(col);var mr=proxy.GetComponent<MeshRenderer>();mr.sharedMaterial=material;mr.shadowCastingMode=ShadowCastingMode.Off;mr.receiveShadows=false;if(Camera.main)Camera.main.depthTextureMode|=DepthTextureMode.Depth;
        }catch(Exception e){Debug.LogException(e,this);Cleanup();enabled=false;}}
        void OnDisable(){Cleanup();}
        void Cleanup(){if(proxy)Destroy(proxy);if(material)Destroy(material);if(field)Destroy(field);proxy=null;material=null;field=null;}
    }
}
