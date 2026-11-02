# Self-run guide data

`catalog/self-run-models.json` is a public snapshot of the hosting catalogue, not an installer support list. Refresh after the hub's facts and overrides change:

```sh
python3 web/scripts/snapshot-self-run.py /path/to/decisionmodels-hosting
```

The snapshot records SHA-256 hashes of model-map.json, model-overrides.json and model-facts.json. It uses dmh.catalog.load_catalog and run_command, requires a pinned revision, confirms a full downloaded checkpoint format, and binds stock vLLM to localhost. Gated weights, adapters, absent or unverified weights and unsupported runtimes receive explanations. Adapter-only weights never become full-model GPU memory estimates. CLI `dm-local plan` requires a known installer catalogue slug (dmlocal/catalog.py:get_model), so these pages do not suggest it.

Commercial permission labels are deliberately conservative: only a plain permissive identifier gets “Commercial use OK”; mixed code/weights terms need model-card review. Non-commercial restrictions are displayed at the top. Serving public weights directly requires no installer licence. No public-weight runtime or cloud CLI recipe was executed end-to-end for this change.

Provider instance names and GPU memory were fetched from the primary sources linked in web/lib/cloud-instances.ts on 2 November 2026. AWS marketing pages report nominal GB; EC2 technical tables can report smaller usable GiB. Memory selection uses the served precision estimate rather than a hypothetical lower precision. Multi-GPU memory alone does not establish model/runtime compatibility. GCP a3-highgpu-1g requires Spot or Flex-start. Azure smaller NVads A10 sizes are fractional GPUs.

`requested=1` is a navigation confirmation after the hub records the hardware request; it is not evidence of a new submission by itself. The existing form still handles pilot interest. Hardware illustrations are original generic SVGs in web/public/hardware, with device-class alternative text.

For screenshot checks, run `node web/scripts/qa/selfservice-shots.cjs` from the repo root after building. It uses a loopback next start and closes its Chromium and server. The script maps the hub asset-prefix path to the local Next asset path for standalone local capture. It records image loading, page errors and viewport overflow alongside the six screenshots. No forms are submitted.

Fix round, 2 November: the snapshot also requires a non-empty architecture list with every entry in the hub's `NATIVE_ARCHS` allowlist. Custom or unknown architectures receive no stock command; remote code is never enabled. The refreshed facts come from hosting commit `8e868d73f81ba43e2103d6bb18100cd9d2888465`.

Cloud links carry `?model=<slug>`. The guide uses the same model memory and instance selection as the model card, fills `INSTANCE_TYPE` in each provider command and includes the pinned model command. Single-GPU capacity takes precedence over aggregate multi-GPU capacity. AWS `p5.4xlarge` provides one 80 GB H100 (https://aws.amazon.com/ec2/instance-types/p5/), sufficient for Mammoth's 67.8 GB estimate. Only when no listed single GPU fits does selection use a fitting multi-GPU instance, adding `--tensor-parallel-size` equal to its GPU count and an explicit untested-serving note. GPU memory fit does not verify attention-head divisibility or runtime compatibility. A2 Ultra local SSD is automatically attached (https://docs.cloud.google.com/compute/docs/accelerator-optimized-machines). Without a model, the guide presents the table first and refuses to create a VM until the user replaces the `INSTANCE_TYPE` placeholder.
