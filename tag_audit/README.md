# Datahub Tag Audit Action
Datahub action to reapply tags that are not permitted for removal

## Features
- reapply tags that should not be deleted
- on each tag removal attempt, send an audit doc to elasticsearch



## Build

```bash
docker build -t datahub-tag-audit-action:v1 . --no-cache
docker push datahub-tag-audit-action:v1
```

## tag_reapply.yaml
```yaml
# tag_reapply.yaml
name: "tag_audit_V0.1"
source:
  type: "kafka"
  config:
    connection:
      bootstrap: ${KAFKA_BOOTSTRAP_SERVER:-localhost:9092}
      schema_registry_url: ${SCHEMA_REGISTRY_URL:-http://localhost:8081}
action:
  type: "reapply_tag:TagReApplicationAction"
  config:
    # Some sample configuration which should be printed on create.
    enabled: true
    tag_prefixes:
      - CI
      - PG
      - Legacy
    es:
      url: "http://localhost:9900"
      username:
      password: 
      max_retries: 3
      retry_delay: 3
      index: datahub_audit
    gms:
      url: "http://localhost:8080"
      token: "eyJhbGciOiJIUzI1NiJ9.eyJhY3RvclR5cGUiOiJVU0VSIiwiYWN0b3JJZCs"


datahub:
  server: http://localhost:8080

```

## Run on prod 
```bash
 docker run -d -v $PWD/tag_reapply.yaml:/tmp/tag_reapply.yaml datahub-tag-audit-action:v1.8 /tmp/tag_reapply.yaml

```

## Check logs
```bash
docker logs -f <container id>
```


## Author
- [@abhishek](mailto:abhifrgn@gmail.com)

