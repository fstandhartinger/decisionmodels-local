import type { Metadata } from "next";
import Link from "next/link";
import { cloudInstanceFor, cloudServeCommand, cloudInstances } from "@/lib/cloud-instances";
import { CopyCommand } from "@/components/copy-command";
import { selfRunModel } from "@/lib/self-run";
import { getModel, isInstallerSupported, installRecipeStatus } from "@/lib/catalog";
import { getHardware } from "@/lib/hardware-all";
import { POSIX_INSTALL_COMMAND } from "@/lib/install-commands";

export const metadata: Metadata = { title: "Run models in your cloud account", alternates: { canonical: "/local/cloud" } };

const aws = `# On your computer: AWS CLI configured; choose a region with GPU capacity.
export AWS_DEFAULT_REGION=eu-central-1
DM_KEY=your-existing-ec2-key-name
DM_KEY_FILE="$HOME/.ssh/your-key.pem"
DM_SUBNET=subnet-REPLACE_ME
DM_VPC=vpc-REPLACE_ME
DM_MY_IP=203.0.113.1/32 # Replace with your public IP /32.
DM_AMI=$(aws ec2 describe-images --owners amazon --filters \
  'Name=name,Values=Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 24.04)*' \
  'Name=architecture,Values=x86_64' 'Name=state,Values=available' \
  --query 'sort_by(Images,&CreationDate)[-1].ImageId' --output text)
[ "$DM_AMI" != None ] || { echo 'No matching AMI in this region'; exit 1; }
DM_SG=$(aws ec2 create-security-group --group-name dm-local-guide \
  --description 'SSH from my IP only' --vpc-id "$DM_VPC" --query GroupId --output text)
aws ec2 authorize-security-group-ingress --group-id "$DM_SG" \
  --protocol tcp --port 22 --cidr "$DM_MY_IP"
DM_VM=$(aws ec2 run-instances --image-id "$DM_AMI" --instance-type "$INSTANCE_TYPE" \
  --key-name "$DM_KEY" --subnet-id "$DM_SUBNET" --security-group-ids "$DM_SG" \
  --associate-public-ip-address --count 1 \
  --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":200,"VolumeType":"gp3","DeleteOnTermination":true}}]' \
  --query 'Instances[0].InstanceId' --output text)
aws ec2 wait instance-running --instance-ids "$DM_VM"
DM_IP=$(aws ec2 describe-instances --instance-ids "$DM_VM" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
ssh -i "$DM_KEY_FILE" ubuntu@"$DM_IP"`;

const azure = `# On your computer: az login first. Pick a region with GPU quota.
DM_REGION=westeurope
DM_GROUP=dm-local-guide # New resource group dedicated to this guide only.
DM_MY_IP=203.0.113.1/32 # Replace with your public IP /32.
az group create --name "$DM_GROUP" --location "$DM_REGION"
# Review available NVIDIA-enabled Ubuntu HPC images in your region.
az vm image list --location "$DM_REGION" --publisher microsoft-dsvm \
  --offer ubuntu-hpc --sku 2204 --all --output table
az network nsg create --resource-group "$DM_GROUP" --name dm-ssh
az network nsg rule create --resource-group "$DM_GROUP" --nsg-name dm-ssh \
  --name MySSH --priority 100 --source-address-prefixes "$DM_MY_IP" \
  --destination-port-ranges 22 --protocol Tcp --access Allow
az vm create --resource-group "$DM_GROUP" --name dm-model \
  --image microsoft-dsvm:ubuntu-hpc:2204:latest \
  --size "$INSTANCE_TYPE" --admin-username dmuser \
  --generate-ssh-keys --nsg dm-ssh --nsg-rule NONE \
  --os-disk-size-gb 200 --public-ip-sku Standard
DM_IP=$(az vm show -g "$DM_GROUP" -n dm-model -d --query publicIps -o tsv)
ssh dmuser@"$DM_IP"`;

const gcp = `# On your computer: gcloud auth login and select your project first.
DM_REGION=us-central1
DM_ZONE=us-central1-a # Check the chosen GPU is available in this zone.
# Dedicated private network; Cloud NAT allows package and weights downloads.
gcloud compute networks create dm-guide-net --subnet-mode=custom
gcloud compute networks subnets create dm-guide-subnet --network dm-guide-net \
  --region "$DM_REGION" --range 10.42.0.0/24
gcloud compute routers create dm-guide-router --network dm-guide-net --region "$DM_REGION"
gcloud compute routers nats create dm-guide-nat --router dm-guide-router \
  --region "$DM_REGION" --nat-all-subnet-ip-ranges --auto-allocate-nat-external-ips
# Uses an IAP SSH tunnel; grant yourself IAP tunnel + SSH permissions first.
gcloud compute firewall-rules create dm-guide-iap-ssh --network dm-guide-net \
  --allow tcp:22 --source-ranges 35.235.240.0/20 --target-tags dm-guide
gcloud compute instances create dm-model --zone "$DM_ZONE" \
  --machine-type "$INSTANCE_TYPE" --image-project deeplearning-platform-release \
  --image-family common-cu129-ubuntu-2204-nvidia-580 \
  --boot-disk-size 200GB --maintenance-policy TERMINATE \
  --metadata install-nvidia-driver=True --tags dm-guide --subnet dm-guide-subnet --no-address
gcloud compute ssh dm-model --zone "$DM_ZONE" --tunnel-through-iap`;

const providers = [
  { id: "aws", name: "AWS", create: aws, note: "Use a subnet with an internet gateway. The security group permits SSH only from your IP. Multi-GPU P instances need tensor parallelism, a compatible attention-head count and enough disk space.", docs: "https://docs.aws.amazon.com/dlami/latest/devguide/what-is-dlami.html", cleanup: `# On your computer, after leaving SSH:\naws ec2 terminate-instances --instance-ids "$DM_VM"\naws ec2 wait instance-terminated --instance-ids "$DM_VM"\naws ec2 delete-security-group --group-id "$DM_SG"`, tunnel: `ssh -i "$DM_KEY_FILE" -N -L 8000:127.0.0.1:8000 ubuntu@"$DM_IP"` },
  { id: "azure", name: "Azure", create: azure, note: "Check image availability and NVIDIA driver compatibility for your chosen size. NVads A10 sizes below NV36 have fractional GPUs (4–12 GB), not a full 24 GB. New A100 capacity is limited; H100 may be available instead.", docs: "https://learn.microsoft.com/en-us/azure/virtual-machines/azure-hpc-vm-images", cleanup: `# Deletes the dedicated group and all its VM, disk and network resources.\naz group delete --name "$DM_GROUP" --yes`, tunnel: `ssh -N -L 8000:127.0.0.1:8000 dmuser@"$DM_IP"` },
  { id: "gcp", name: "Google Cloud", create: gcp, note: "A3 single-GPU H100 requires Spot or Flex-start; it is not an ordinary on-demand VM. A2 Ultra includes automatically attached local SSD storage, which is lost when the VM is deleted. IAP access requires IAM permissions and the IAP API. The example creates a private network and Cloud NAT for outbound downloads; NAT and its public IP also incur charges.", docs: "https://docs.cloud.google.com/deep-learning-vm/docs/images", cleanup: `# On your computer; also deletes the auto-delete boot disk.\ngcloud compute instances delete dm-model --zone "$DM_ZONE" --quiet\ngcloud compute firewall-rules delete dm-guide-iap-ssh --quiet\ngcloud compute routers delete dm-guide-router --region "$DM_REGION" --quiet\ngcloud compute networks subnets delete dm-guide-subnet --region "$DM_REGION" --quiet\ngcloud compute networks delete dm-guide-net --quiet`, tunnel: `gcloud compute ssh dm-model --zone "$DM_ZONE" --tunnel-through-iap -- -N -L 8000:127.0.0.1:8000` }
];

function Command({ value }: { value: string }) {
  return <><pre className="code-block">{value}</pre><CopyCommand value={value} /></>;
}

export default async function CloudPage({ searchParams }: { searchParams?: Promise<{ model?: string | string[] }> }) {
  const query = await searchParams;
  const slug = typeof query?.model === "string" ? query.model : undefined;
  const facts = slug ? selfRunModel(slug) : undefined;
  const model = slug ? getModel(slug) : undefined;
  const hardware = slug ? getHardware(slug) : undefined;
  const supported = model && isInstallerSupported(model);
  const variant = model?.variants?.filter((v) => installRecipeStatus(v) !== "documentation_only" && v.platforms?.includes("linux-nvidia") && Number(v.min_vram_gb) > 0)
    .sort((a, b) => Number(a.min_vram_gb) - Number(b.min_vram_gb))[0];
  const memory = supported ? (hardware ? hardware.min?.vram_gb : variant?.min_vram_gb) : facts?.vram_gb;
  const name = facts?.name ?? model?.name ?? slug;

  return <div className="cloud-quick-guide">
    <section className="section-wrap hero"><p className="eyebrow"><Link href="/local">Run locally</Link> / Your cloud account</p><h1>Run models in your cloud account</h1><p className="lede space-top-sm">Create a GPU VM, connect over SSH, run your model, then delete the machine.</p><p>Commands have not been run by us end-to-end. You need a cloud account, billing, its CLI and GPU quota in your chosen region. GPU quota requests and capacity checks may be needed before launch. You pay the provider directly.</p>{slug && <div className="callout space-top"><strong>{name}</strong><p>GPU memory needed: {memory ? `${memory} GB` : "unknown; confirm sizing before renting"}. {facts?.command ? "Estimates use the served precision and 8k context." : facts?.missing ?? "A stock vLLM command has not been verified for this model."}</p><Link href={`/models/${encodeURIComponent(slug)}/local`}>Model setup and licence →</Link></div>}<nav className="hero-actions">{providers.map((p) => <a className="button button-secondary" href={`#${p.id}`} key={p.id}>{p.name}</a>)}</nav></section>
    {providers.map((provider) => {
      const instance = cloudInstanceFor(provider.id, memory);
      const serve = cloudServeCommand(facts?.command, instance);
      const create = `INSTANCE_TYPE=${instance?.name ?? "REPLACE_WITH_INSTANCE_FROM_TABLE"}\n: "${"${INSTANCE_TYPE:?Choose an instance by GPU memory first}"}"\n[ "$INSTANCE_TYPE" != REPLACE_WITH_INSTANCE_FROM_TABLE ] || { echo 'Choose INSTANCE_TYPE from the table first'; exit 1; }\n${provider.create}`;
      return <section className="section-wrap section" id={provider.id} key={provider.id}>
      <p className="section-kicker">Your cloud account</p><h2>{provider.name}</h2>
      <p>Choose by GPU memory first: one GPU must fit the model. If none fits, use a multi-GPU instance with tensor parallelism. Also check system RAM, disk and runtime compatibility. Figures below describe the hardware, not a tested model setup.</p>
      <div className="table-wrap"><table><thead><tr><th>Instance type</th><th>GPU</th><th>Memory per GPU</th><th>Total GPU memory</th></tr></thead><tbody>{cloudInstances.filter((item) => item.provider === provider.id).map((item) => <tr key={item.name}><td>{item.name}</td><td>{item.gpu}</td><td>{item.gpuMemory} GB</td><td>{item.memory} GB</td></tr>)}</tbody></table></div>
      <p className="source-note">Provider specifications (checked 2 November 2026): {[...new Set(cloudInstances.filter((item) => item.provider === provider.id).map((item) => item.source))].map((url, i) => <span key={url}>{i > 0 && " · "}<a href={url}>GPU specifications {i + 1}</a></span>)}</p>
      {instance && <div className="callout"><p>For {name}: {memory} GB needed → <strong>{instance.name}</strong> ({instance.gpu}; {instance.gpuMemory} GB per GPU).</p>{instance.gpuCount > 1 && <p>No single GPU listed here fits. Use <code>--tensor-parallel-size {instance.gpuCount}</code>. Multi-GPU serving has not been tested by us. Check model attention-head divisibility and runtime compatibility before launch.</p>}</div>}
      {slug && !instance && <p>No verified instance in this guide fits the recorded requirement. Confirm memory and runtime compatibility before creating a VM.</p>}
      <p>{provider.note}</p>
      <h3 className="space-top">1. Create a VM and connect</h3><p>Replace the example IP, key and network values first. The example creates a 200 GB boot disk; increase it if your model needs more space.</p><Command value={create} />
      <p className="source-note"><a href={provider.docs}>Provider image and setup documentation</a></p>
      <h3 className="space-top">2. Install and run inside the SSH session</h3><p>Check the driver with <code>nvidia-smi</code>. Cloud GPU images can ship an older driver: recipes using CUDA 13 need an R580 or newer compatible NVIDIA driver. Check the <a href="https://docs.nvidia.com/deploy/cuda-compatibility/minor-version-compatibility.html">NVIDIA driver requirements</a> and your provider’s image instructions before installing. The CUDA version shown by <code>nvidia-smi</code> is the driver’s supported version.</p><p>For a model with a supported installer recipe, check the plan first, then install:</p><Command value={`${POSIX_INSTALL_COMMAND}\n# Replace MODEL_SLUG with a supported model from /local.\ndm-local plan MODEL_SLUG\ndm-local install MODEL_SLUG`} />
      <p>For public weights without an installer recipe, copy the pinned vLLM command from that model’s local page after installing vLLM in a virtual environment:</p><Command value={"python3 -m venv .venv\n. .venv/bin/activate\npython -m pip install vllm"} />
      {serve && <><p>Run this pinned command for {name} on the selected {instance?.name}:</p><Command value={serve} /></>}
      {slug && !serve && <p>{facts?.missing ?? "No verified vLLM command and fitting instance are available together; follow the model card before renting."}</p>}
      <p>Run the model page’s <code>vllm serve</code> command here. Keep <code>--host 127.0.0.1 --port 8000</code>. Do not open ports 8000 or 8484 to the internet. Review any custom model code before running it.</p>
      <h3 className="space-top">3. Reach localhost through a tunnel</h3><p>In a second terminal on your computer (keep the model running):</p><Command value={provider.tunnel} /><p>Then connect to <code>http://127.0.0.1:8000</code>. For the installer endpoint, replace both occurrences of 8000 with 8484.</p>
      <h3 className="space-top">4. Delete the resources</h3><p>Exit SSH, then run the following on your computer. Check the provider console for remaining disks or addresses; stopped VMs can still incur storage charges.</p><Command value={provider.cleanup} />
    </section>; })}
  </div>;
}
