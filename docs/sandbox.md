# Sandbox and submission model

Status: proposed, blocking the runner.

## Two tiers of submission

**Tier 1, exported graphs.** Each env publishes an observation and action spec. Entrants upload an ONNX model. We run inference in our own harness, so no untrusted code executes.

ONNX carries the computation graph, not only the weights, so architecture is not constrained. Any depth, any topology, attention, convolutions, residual stacks, whatever the exporter emits. We run a model we have never seen knowing only its input and output shapes. A pure-tensor format like safetensors cannot do this, since loading it requires already knowing the architecture, which would force every entrant into a fixed menu of model classes.

A graph is not code. ONNX is dataflow over a fixed operator set with no syscalls, no filesystem, and no unbounded control flow. Three rules make that hold:

- Allowlist operators. The check is not "is this ONNX" but "does this graph use only allowlisted ops with no custom operators." Custom ops load native libraries, which is code execution through the side door.
- Run it in the sandbox anyway. ONNX Runtime is C++ parsing untrusted input and has had parser CVEs. Isolation here is defense in depth, just a far cheaper sandbox than tier 2 needs.
- Declare recurrent state. A stateful policy carries hidden state between steps, which in ONNX means extra graph inputs and outputs. The env spec defines them, or the runner cannot thread them.

Never call `torch.load` on user bytes. Pickle is arbitrary code execution wearing a checkpoint costume. Avoid TorchScript as a middle ground too: it also carries a graph, but its interpreter surface is much wider than ONNX Runtime's and closer to running code than it looks.

**Tier 2, arbitrary code.** Search is the reason, not architecture. MCTS, rollouts, and anything with data-dependent control flow and a variable compute budget is not a static graph and never will be. Hand-written heuristics land here too. Build it after tier 1 has users.

## Isolation

Plain Docker is not the boundary. Containers share the host kernel and root in the container is one bug away from root on the host. Anything running untrusted code needs gVisor or a microVM underneath.

Use Modal. It runs workloads under gVisor, cold starts in under a second, bills per second, and is Python-native so submissions need no translation layer. The decisive factor is fan-out: thousands of concurrent matches without us writing and operating a scheduler.

Alternatives considered. Fly Machines gives Firecracker isolation and is cheaper at sustained load, at the cost of running more ourselves. Self-hosted Kubernetes with gVisor means owning a scheduler, a registry, and a warm pool, which is a team we do not have. E2B and Cloudflare Sandbox SDK target short interactive execution rather than sustained compute, so they are the wrong shape for a match running millions of env steps.

## Where the env and policies live

This is the load-bearing decision.

One sandbox per policy plus a separate env process needs an IPC round trip per step. Ocean envs run millions of steps per second in C, so per-step IPC makes a two-second match take twenty minutes. Not viable.

One shared container for env and both policies has acceptable latency but puts two untrusted policies in one address space with each other and with the env. Policy A can read B's state or write the reward.

**Resolution: batch across matches.** PufferLib is vectorized, so run N matches concurrently and let each IPC round trip carry N observations. At N in the hundreds the per-step overhead amortizes away and each policy keeps its own sandbox. Batch size is a platform parameter, not a tuning knob, and the runner is designed around it from the start.

## Sandbox constraints

Enforced for every tier-2 match:

- No network egress.
- Wall-clock limit and a separate step-count limit. A policy that returns instantly and never terminates the episode is the common failure mode, and a time limit alone does not catch it.
- Memory cap, enforced by the platform rather than by the process.
- Read-only filesystem except one scratch directory, discarded after the match.
- No environment variables, no secrets, no credentials in the container.
- The runner injects the seed. The policy never reads it and never sources its own entropy.
- Results leave only as a structured payload the runner parses. Anything else on stdout is logged and ignored.

## Open questions

- Does a batched C env produce identical bytes across different host CPUs? Float accumulation may say no. Test on two machines before the leaderboard depends on reproducibility.
- Cheating detection when a match is disputed. One option is re-running with policies fully isolated and comparing. Needs a cost estimate.
- GPU policies. Modal has GPUs, but per-match GPU allocation changes the cost model. Defer until someone submits a model that needs one.
