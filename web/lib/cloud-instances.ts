/** Provider specifications checked against the linked public docs on 2 November 2026. */
export const cloudInstances = [
  { provider: "aws", name: "g6.xlarge", gpu: "1 × L4", memory: 24, source: "https://aws.amazon.com/ec2/instance-types/g6/" },
  { provider: "aws", name: "g6e.xlarge", gpu: "1 × L40S", memory: 48, source: "https://aws.amazon.com/ec2/instance-types/g6e/" },
  { provider: "aws", name: "p5.48xlarge", gpu: "8 × H100 (80 GB each)", memory: 640, source: "https://aws.amazon.com/ec2/instance-types/p5/" },
  { provider: "aws", name: "p4de.24xlarge", gpu: "8 × A100 (80 GB each)", memory: 640, source: "https://aws.amazon.com/ec2/instance-types/p4/" },
  { provider: "azure", name: "Standard_NV36ads_A10_v5", gpu: "1 × A10", memory: 24, source: "https://learn.microsoft.com/en-us/azure/virtual-machines/sizes/gpu-accelerated/nvadsa10v5-series" },
  { provider: "azure", name: "Standard_NC24ads_A100_v4", gpu: "1 × A100", memory: 80, source: "https://learn.microsoft.com/en-us/azure/virtual-machines/sizes/gpu-accelerated/nca100v4-series" },
  { provider: "azure", name: "Standard_NC40ads_H100_v5", gpu: "1 × H100 NVL", memory: 94, source: "https://learn.microsoft.com/en-us/azure/virtual-machines/sizes/gpu-accelerated/ncadsh100v5-series" },
  { provider: "gcp", name: "g2-standard-8", gpu: "1 × L4", memory: 24, source: "https://docs.cloud.google.com/compute/docs/gpus" },
  { provider: "gcp", name: "a2-ultragpu-1g", gpu: "1 × A100", memory: 80, source: "https://docs.cloud.google.com/compute/docs/gpus" },
  { provider: "gcp", name: "a3-highgpu-1g", gpu: "1 × H100 (Spot or Flex-start only)", memory: 80, source: "https://docs.cloud.google.com/compute/docs/gpus" }
] as const;

export function cloudInstanceFor(provider: string, memory?: number | null) {
  if (!memory || memory <= 0) return undefined;
  return cloudInstances.filter((item) => item.provider === provider && item.memory >= memory).sort((a, b) => a.memory - b.memory)[0];
}
