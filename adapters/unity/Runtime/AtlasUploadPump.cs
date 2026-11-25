using System;
namespace VaporGame.Unity
{
    /// <summary>Game-thread pump. CPU stays on its direct synchronous packing path;
    /// GPU/Hybrid use one ticket and keep the last complete texture until ready.
    /// No call here waits for GPU completion. Simulation step and Texture.Apply costs remain.
    /// </summary>
    internal sealed class AtlasUploadPump
    {
        private readonly Simulation runtime;
        private readonly byte[] output;
        private AtlasTicket ticket;
        private ulong epoch;
        internal AtlasUploadPump(Simulation runtime,byte[] output)
        {this.runtime=runtime;this.output=output;epoch=runtime.AtlasEpoch;}
        internal bool SynchronizeReset()
        {var next=runtime.AtlasEpoch;if(next==epoch)return false;epoch=next;ticket=default;Array.Clear(output,0,output.Length);return true;}
        internal bool Poll()
        {
            if(ticket.Id==0)return false;
            try{if(!runtime.TryPollAtlas(ticket,output))return false;}
            catch{ticket=default;throw;}
            ticket=default;return true;
        }
        internal bool Request()
        {
            if(runtime.Backend.Active==BackendMode.Cpu){runtime.CopyAtlas(output);return true;}
            if(ticket.Id!=0)return false;
            if(!runtime.TryBeginAtlas(out ticket))return false;
            return false; // Never poll/wait in the submission path.
        }
    }
}
