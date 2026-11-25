using System;
using UnityEngine;
using UnityEngine.Rendering;
namespace VaporGame.Unity {
    [DisallowMultipleComponent]
    public sealed class VaporEffectVolume:MonoBehaviour {
        public EffectId preset=EffectId.CumulusCloud;
        public EffectQuality quality=EffectQuality.Medium;
        public BackendMode backend=BackendMode.Cpu;
        [Range(1,4)]public int detailScale=1;
        public bool playOnEnable=true,allowCpuFallback=false;
        public Transform emitterTransform;
        public Renderer emberRenderer;
        [Range(0,1)]public float ashProgress;
        MaterialPropertyBlock emberBlock;
        public Shader volumeShader;
        public Camera lodCamera;
        Effect effect;Texture2D atlas;Material material;GameObject proxy;Vector3 extent;byte[] pixels;double elapsed;AtlasUploadPump uploadPump;
        public Effect Runtime=>effect;
        void OnEnable(){try{
            if((transform.lossyScale-Vector3.one).sqrMagnitude>1e-6f)throw new InvalidOperationException("Vapor volume requires a unit-scale root.");
            effect=new Effect(preset,quality,BackendOptions.For(backend,(uint)detailScale,allowCpuFallback));var d=effect.Definition;var c=d.Config;
            var b=effect.Runtime?.Backend;int nx=(int)(b.HasValue?b.Value.RenderNx:c.Nx),ny=(int)(b.HasValue?b.Value.RenderNy:c.Ny),nz=(int)(b.HasValue?b.Value.RenderNz:c.Nz);
            if(nx>SystemInfo.maxTextureSize||checked(ny*nz)>SystemInfo.maxTextureSize)throw new InvalidOperationException("Atlas exceeds texture size; choose lower quality.");
            extent=new Vector3(c.Nx,c.Ny,c.Nz)*c.CellSize;pixels=new byte[checked(effect.RenderVoxelCount*4)];atlas=new Texture2D(nx,ny*nz,TextureFormat.RGBA32,false,true){wrapMode=TextureWrapMode.Clamp,filterMode=FilterMode.Bilinear};
            if(!volumeShader)volumeShader=Shader.Find(GraphicsSettings.currentRenderPipeline?"Vapor/VolumeURP":"Vapor/VolumeBuiltIn");if(!volumeShader||!volumeShader.isSupported)throw new InvalidOperationException("Assign a supported Vapor shader.");
            material=new Material(volumeShader);material.SetTexture("_Atlas",atlas);material.SetVector("_Grid",new Vector4(nx,ny,nz,0));material.SetVector("_Extent",extent);material.SetFloat("_DensityCap",c.DensityCap);var m=d.Material;material.SetColor("_Colour",new Color(m.Colour.X,m.Colour.Y,m.Colour.Z,1));material.SetFloat("_Extinction",m.Extinction);material.SetFloat("_Steps",d.RaySteps);material.SetFloat("_Anisotropy",m.Anisotropy);material.SetFloat("_Albedo",m.Albedo);material.SetFloat("_Emission",m.Emission);material.SetFloat("_Ambient",m.Ambient);material.SetFloat("_ThermalFade",m.ThermalFade);
            proxy=GameObject.CreatePrimitive(PrimitiveType.Cube);proxy.name="Vapor Effect Volume";proxy.layer=gameObject.layer;proxy.transform.SetParent(transform,false);proxy.transform.localPosition=extent*.5f;proxy.transform.localScale=extent;var collider=proxy.GetComponent<Collider>();if(collider)Destroy(collider);var mr=proxy.GetComponent<MeshRenderer>();mr.sharedMaterial=material;mr.shadowCastingMode=ShadowCastingMode.Off;mr.receiveShadows=false;
            if(!lodCamera)lodCamera=Camera.main;if(lodCamera)lodCamera.depthTextureMode|=DepthTextureMode.Depth;
            if(effect.Runtime!=null)uploadPump=new AtlasUploadPump(effect.Runtime,pixels);
            UpdatePose();if(playOnEnable)effect.Play();ApplyPixels();RequestUpload();
        }catch(Exception e){Debug.LogException(e,this);Cleanup();enabled=false;}}
        void UpdatePose(){if(effect?.Runtime==null||!emitterTransform)return;Vector3 p=transform.InverseTransformPoint(emitterTransform.position),d=transform.InverseTransformDirection(emitterTransform.forward);effect.SetPose(new Float3(p.x,p.y,extent.z-p.z),new Float3(d.x,d.y,-d.z));}
        public void PlayEffect(){effect?.Play();}public void StopEffect(){effect?.Stop();}public void ResetEffect(){if(effect==null)return;effect.Reset();if(uploadPump!=null)uploadPump.SynchronizeReset();Array.Clear(pixels,0,pixels.Length);ApplyPixels();RequestUpload();}
        void Update(){if(effect==null)return;try{if(uploadPump!=null){if(uploadPump.SynchronizeReset())ApplyPixels();if(uploadPump.Poll())ApplyPixels();}UpdatePose();effect.Advance(Time.deltaTime);var d=effect.Definition;if(d.Ember!=0&&emberRenderer){var visual=EmberVisual.At(effect.Time,ashProgress,effect.Playing);if(emberBlock==null)emberBlock=new MaterialPropertyBlock();emberRenderer.GetPropertyBlock(emberBlock);emberBlock.SetColor("_EmissionColor",new Color(visual.Colour.X,visual.Colour.Y,visual.Colour.Z)*visual.Intensity);emberRenderer.SetPropertyBlock(emberBlock);}float distance=lodCamera?Vector3.Distance(lodCamera.transform.position,proxy.transform.position)/Math.Max(.0001f,extent.magnitude*.5f):0;bool visible=distance<100;proxy.SetActive(visible);if(!visible)return;int steps=distance<4?(int)d.RaySteps:distance<12?Math.Max(16,(int)(d.RaySteps*.65f)):24;float hz=distance<4?d.UploadHz:distance<12?Math.Min(10u,d.UploadHz):2;material.SetFloat("_Steps",steps);elapsed+=Time.deltaTime;if(elapsed>=1.0/hz){elapsed%=1.0/hz;RequestUpload();}}catch(Exception e){Debug.LogException(e,this);enabled=false;}}
        void RequestUpload(){if(uploadPump==null){effect.CopyAtlas(pixels);ApplyPixels();}else if(uploadPump.Request())ApplyPixels();}
        void ApplyPixels(){atlas.LoadRawTextureData(pixels);atlas.Apply(false,false);}
        void OnDisable(){Cleanup();}void Cleanup(){uploadPump=null;effect?.Dispose();effect=null;if(proxy)Destroy(proxy);if(material)Destroy(material);if(atlas)Destroy(atlas);proxy=null;material=null;atlas=null;pixels=null;elapsed=0;}
    }
}
