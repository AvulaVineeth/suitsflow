# Deployment Architecture

## Environments

Local development uses Docker Compose for the API, PostgreSQL, Redis, object-storage emulator where useful, and supporting services. Configuration is environment-specific; secrets are never committed.

## AWS target

| Service | Responsibility |
|---|---|
| API Gateway | Public API entry and request controls |
| ECS/Fargate | FastAPI, agent, and MCP services |
| Lambda and queue | Asynchronous document processing and event work |
| S3 | Original documents and extracted artifacts |
| Aurora PostgreSQL | Transactional system of record |
| Redis | Cache and short-lived coordination |
| Bedrock | Claude model inference |
| Secrets Manager, IAM | Secrets and least-privilege access |
| CloudWatch | Infrastructure logs, metrics, alarms |

Terraform provisions environment-scoped infrastructure. CI validates formatting, types, unit/integration/evaluation suites, builds immutable container images, and promotes only approved artifacts.

## Initial implementation

Containerize the API and run the full vertical slice locally. Add Terraform and AWS deployment only after the local security, data, and agent contracts are covered by automated tests.
