## 0 H.A.G.A.R.

Harness Agentico Generale per AI Resilienti (General Agentic Harness for Resilient AIs)


# 1. Project Vision

Hagar is an LLM harness developed in Python, designed for the resilient execution of LLMs.

The goal is not merely to provide a chat interface with a language model, but to create a ***secure*** operating environment in which an LLM can use tools, consult persistent memory, and interact with external systems — all without having direct access to the host machine's actual resources — while preventing or at least mitigating common errors.

To this end, we adopt principles and methodologies from HMI/HCI (Human-Machine Interface/Interaction for industrial machinery) and Cognitive Ergonomics, applying them to the design of the environment in which the LLM operates. As a first iteration of the project, we define **The Four Laws of HAGAR**:

## 1.1 First Law of HAGAR
**An LLM is, by definition, untrustworthy.** This is not because it is malicious or useless, but because it is probabilistic. Therefore, every statement it makes must be verified, and every action it takes must be constrained.

## 1.2 Second Law of HAGAR
**Tools are more reliable than the LLM.** If the filesystem indicates that a file exists, it exists. If a tool returns a file size, that size is real. The LLM interprets, but tools provide measurements.

## 1.3 Third Law of HAGAR
**State must exist outside the LLM’s "mind."** By implementing components such as `ToolRegistry`, `MCP`, `FilesystemSandbox`, and (forthcoming) `PermissionEvaluator`, we shift knowledge and control outside of the model itself. This aligns with standard practices for safety-critical systems. 

## 1.4 HAGAR’s Fourth Law
**Every action must be explainable after the fact.** An audit log is essential: when something goes wrong — and eventually it will — the question should not be "Why did the LLM go haywire?" but rather: "What assumption did it make?" "Which tool did it use?" "Which piece of data was incorrect?" In other words: incident investigation — much like in aviation.

## 1.5 Software Architecture

Structurally, HAGAR is built upon five fundamental principles:

- separation between the model and the operating system;
- security by default;
- a plugin-based architecture;
- independence from any specific LLM provider;
- extensibility via tools and the MCP (Model Context Protocol).

---

# 2. Absolute Prohibitions

The model must never:

- directly access the host filesystem;
- execute commands in the actual shell;
- obtain privileges beyond those defined in its configuration;
- have knowledge of the operating system's actual organization.

All operations must take place exclusively through tools that are registered and controlled by the harness.