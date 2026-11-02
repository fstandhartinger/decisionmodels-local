/** Provider specifications checked against the linked public docs on 2 November 2026. */
export const cloudInstances = [
  { provider: "aws", name: "g6.xlarge", gpu: "1 × L4", memory: 24, gpuCount: 1, gpuMemory: 24, source: "https://aws.amazon.com/ec2/instance-types/g6/" },
  { provider: "aws", name: "g6e.xlarge", gpu: "1 × L40S", memory: 48, gpuCount: 1, gpuMemory: 48, source: "https://aws.amazon.com/ec2/instance-types/g6e/" },
  { provider: "aws", name: "p5.4xlarge", gpu: "1 × H100", memory: 80, gpuCount: 1, gpuMemory: 80, source: "https://aws.amazon.com/ec2/instance-types/p5/" },
  { provider: "aws", name: "p5.48xlarge", gpu: "8 × H100 (80 GB each)", memory: 640, gpuCount: 8, gpuMemory: 80, source: "https://aws.amazon.com/ec2/instance-types/p5/" },
  { provider: "aws", name: "p4de.24xlarge", gpu: "8 × A100 (80 GB each)", memory: 640, gpuCount: 8, gpuMemory: 80, source: "https://aws.amazon.com/ec2/instance-types/p4/" },
  { provider: "azure", name: "Standard_NV36ads_A10_v5", gpu: "1 × A10", memory: 24, gpuCount: 1, gpuMemory: 24, source: "https://learn.microsoft.com/en-us/azure/virtual-machines/sizes/gpu-accelerated/nvadsa10v5-series" },
  { provider: "azure", name: "Standard_NC24ads_A100_v4", gpu: "1 × A100", memory: 80, gpuCount: 1, gpuMemory: 80, source: "https://learn.microsoft.com/en-us/azure/virtual-machines/sizes/gpu-accelerated/nca100v4-series" },
  { provider: "azure", name: "Standard_NC40ads_H100_v5", gpu: "1 × H100 NVL", memory: 94, gpuCount: 1, gpuMemory: 94, source: "https://learn.microsoft.com/en-us/azure/virtual-machines/sizes/gpu-accelerated/ncadsh100v5-series" },
  { provider: "azure", name: "Standard_NC80adis_H100_v5", gpu: "2 × H100 NVL (94 GB each)", memory: 188, gpuCount: 2, gpuMemory: 94, source: "https://learn.microsoft.com/en-us/azure/virtual-machines/sizes/gpu-accelerated/ncadsh100v5-series" },
  { provider: "gcp", name: "g2-standard-8", gpu: "1 × L4", memory: 24, gpuCount: 1, gpuMemory: 24, source: "https://docs.cloud.google.com/compute/docs/gpus" },
  { provider: "gcp", name: "a2-ultragpu-1g", gpu: "1 × A100", memory: 80, gpuCount: 1, gpuMemory: 80, source: "https://docs.cloud.google.com/compute/docs/gpus" },
  { provider: "gcp", name: "a2-ultragpu-2g", gpu: "2 × A100 (80 GB each)", memory: 160, gpuCount: 2, gpuMemory: 80, source: "https://docs.cloud.google.com/compute/docs/gpus" },
  { provider: "gcp", name: "a3-highgpu-1g", gpu: "1 × H100 (Spot or Flex-start only)", memory: 80, gpuCount: 1, gpuMemory: 80, source: "https://docs.cloud.google.com/compute/docs/gpus" }
] as const;

/** vLLM uses 90 % of GPU memory by default, so an estimate must fit within this share of the GPUs. */
export const GPU_MEMORY_UTILISATION = 0.9;

export function cloudInstanceFor(provider: string, memory?: number | null) {
  if (!memory || memory <= 0) return undefined;
  const options = cloudInstances.filter((item) => item.provider === provider);
  const usable = (gpuMemory: number) => gpuMemory * GPU_MEMORY_UTILISATION >= memory;
  const single = options.filter((item) => item.gpuCount === 1 && usable(item.gpuMemory))
    .sort((a, b) => a.gpuMemory - b.gpuMemory)[0];
  return single ?? options.filter((item) => item.gpuCount > 1 && usable(item.memory))
    .sort((a, b) => a.gpuCount - b.gpuCount || a.memory - b.memory)[0];
}

export function cloudServeCommand(command: string | null | undefined, instance: ReturnType<typeof cloudInstanceFor>) {
  if (!command || !instance) return null;
  return instance.gpuCount > 1 ? `${command} --tensor-parallel-size ${instance.gpuCount}` : command;
}
