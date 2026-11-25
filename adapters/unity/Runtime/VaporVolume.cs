using System;
using UnityEngine;
using UnityEngine.Rendering;
namespace VaporGame.Unity
{
    /// <summary>One bounded local volume. Transform scale must be 1; rotation/translation supported.</summary>
    [DisallowMultipleComponent]
    public sealed class VaporVolume:MonoBehaviour
    {
        public Vector3Int cells=new Vector3Int(16,20,16);
        [Min(.001f)]public float cellSize=.04f;
        [Range(1,60)]public int uploadHz=20;
        public Transform emitterTransform;
        [Min(.001f)]public float sourceRadius=.05f;
        [Min(0)]public float sourceSpeed=1f,sourceDensityRate=8f;
        public Shader volumeShader;
        public bool paused;
        public BackendMode backend=BackendMode.Cpu;
        [Range(1,4)]public int detailScale=1;
        public bool allowCpuFallback=false,allowSoftwareGpu=false;
        [Range(0,2)]public float detailTurbulence=0;
        [Range(.1f,100)]public float detailFrequency=8;
        private Simulation sim;private Texture2D atlas;private Material material;private GameObject proxy;
        private byte[] bytes;private Vector3 extent;private double uploadTime;private AtlasUploadPump uploadPump;
        public Simulation Runtime=>sim;
        void OnEnable()
        {
#if UNITY_WEBGL && !UNITY_EDITOR
            Debug.LogError("Vapor native Unity adapter is not a Unity WebGL plugin. Use the browser WASM SDK.",this);enabled=false;return;
#else
            try{
                if((transform.lossyScale-Vector3.one).sqrMagnitude>1e-6f)throw new InvalidOperationException("Vapor root transform must have unit scale.");
                if(cells.x<4||cells.y<4||cells.z<4)throw new ArgumentOutOfRangeException(nameof(cells));
                var cfg=Config.Default;cfg.Nx=(uint)cells.x;cfg.Ny=(uint)cells.y;cfg.Nz=(uint)cells.z;cfg.CellSize=cellSize;
                var execution=BackendOptions.For(backend,(uint)detailScale,allowCpuFallback,allowSoftwareGpu);
                execution.DetailTurbulence=detailTurbulence;execution.DetailFrequency=detailFrequency;
                sim=new Simulation(cfg,execution);
                var renderCells=new Vector3Int((int)sim.Backend.RenderNx,(int)sim.Backend.RenderNy,(int)sim.Backend.RenderNz);
                if(renderCells.x>SystemInfo.maxTextureSize||checked(renderCells.y*renderCells.z)>SystemInfo.maxTextureSize)throw new InvalidOperationException("Vapor atlas exceeds GPU maximum texture size; reduce detailScale/grid.");
                extent=new Vector3(cells.x,cells.y,cells.z)*cellSize;bytes=new byte[checked(sim.RenderVoxelCount*4)];
                atlas=new Texture2D(renderCells.x,checked(renderCells.y*renderCells.z),TextureFormat.RGBA32,false,true){name="Vapor density atlas",wrapMode=TextureWrapMode.Clamp,filterMode=FilterMode.Bilinear};
                if(!volumeShader)volumeShader=Shader.Find(GraphicsSettings.currentRenderPipeline?"Vapor/VolumeURP":"Vapor/VolumeBuiltIn");
                if(!volumeShader||!volumeShader.isSupported)throw new InvalidOperationException("Assign a supported Vapor shader; HDRP requires a custom integration.");
                material=new Material(volumeShader);material.SetTexture("_Atlas",atlas);material.SetVector("_Grid",new Vector4(renderCells.x,renderCells.y,renderCells.z,0));material.SetVector("_Extent",new Vector4(extent.x,extent.y,extent.z,0));material.SetFloat("_DensityCap",cfg.DensityCap);
                proxy=GameObject.CreatePrimitive(PrimitiveType.Cube);proxy.name="Vapor Volume Proxy";proxy.layer=gameObject.layer;proxy.transform.SetParent(transform,false);proxy.transform.localPosition=extent*.5f;proxy.transform.localScale=extent;
                var collider=proxy.GetComponent<Collider>();if(collider)Destroy(collider);
                var render=proxy.GetComponent<MeshRenderer>();render.sharedMaterial=material;render.shadowCastingMode=ShadowCastingMode.Off;render.receiveShadows=false;
                uploadPump=new AtlasUploadPump(sim,bytes);UpdateEmitter();ApplyPixels();RequestUpload();
                if(Camera.main)Camera.main.depthTextureMode|=DepthTextureMode.Depth;
            }catch(Exception e){Debug.LogException(e,this);Cleanup();enabled=false;}
#endif
        }
        public Float3 WorldToCorePoint(Vector3 world)
        {var p=transform.InverseTransformPoint(world);return new Float3(p.x,p.y,extent.z-p.z);}
        public Float3 WorldToCoreDirection(Vector3 world)
        {var p=transform.InverseTransformDirection(world);return new Float3(p.x,p.y,-p.z);}
        void UpdateEmitter()
        {
            var e=Emitter.Default;
            e.Position=emitterTransform?WorldToCorePoint(emitterTransform.position):new Float3(extent.x*.5f,.1f,extent.z*.5f);
            e.Direction=emitterTransform?WorldToCoreDirection(emitterTransform.forward):new Float3(.1f,1f,0f);
            e.Radius=sourceRadius;e.Speed=sourceSpeed;e.DensityRate=sourceDensityRate;sim.SetEmitter(0,e);
        }
        public void SetCapsule(uint id,Vector3 worldA,Vector3 worldB,float radius,Vector3 worldVelocity)
        {if(sim==null)throw new InvalidOperationException("Vapor is disabled");sim.SetObstacle(id,Obstacle.Capsule(WorldToCorePoint(worldA),WorldToCorePoint(worldB),radius,WorldToCoreDirection(worldVelocity)));}
        void Update()
        {
            if(sim==null)return;
            try{
                if(uploadPump.SynchronizeReset())ApplyPixels();
                if(uploadPump.Poll())ApplyPixels();
                if(paused)return;
                UpdateEmitter();sim.Advance(Time.deltaTime);uploadTime+=Time.deltaTime;
                if(uploadTime>=1.0/Math.Max(1,uploadHz)){uploadTime%=1.0/Math.Max(1,uploadHz);RequestUpload();}
            }
            catch(Exception e){Debug.LogException(e,this);paused=true;}
        }
        void RequestUpload(){if(uploadPump.Request())ApplyPixels();}
        void ApplyPixels(){atlas.LoadRawTextureData(bytes);atlas.Apply(false,false);}
        void OnDisable(){Cleanup();}
        void Cleanup(){uploadPump=null;sim?.Dispose();sim=null;if(proxy)Destroy(proxy);if(material)Destroy(material);if(atlas)Destroy(atlas);proxy=null;material=null;atlas=null;bytes=null;uploadTime=0;}
    }
}
