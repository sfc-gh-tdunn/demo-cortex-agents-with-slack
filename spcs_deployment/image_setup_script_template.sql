-- 1. Set up the Database and Schema for the Image Repository
USE ROLE ACCOUNTADMIN;

CREATE DATABASE IF NOT EXISTS <database-name>;
CREATE SCHEMA IF NOT EXISTS <database-name>.<schema-name>;
USE SCHEMA <database-name>.<schema-name>;

-- 2. Create the Image Repository
CREATE IMAGE REPOSITORY IF NOT EXISTS <repo-name>;
SHOW IMAGE REPOSITORIES; 
-- Note the 'repository_url' from the command above. 
-- You will tag your Docker image with this URL. 
-- e.g. <org>-<account>.registry.snowflakecomputing.com/<database-name>/apps/<repo-name>/cortex_slack_bot:latest
-- 3. Create Network Rules to allow outbound access to Slack and Snowflake
-- SPCS containers block outbound internet by default.
-- You need to allow traffic to Slack API and Websockets.

CREATE OR REPLACE NETWORK RULE SLACK_NETWORK_RULE
  MODE = EGRESS
  TYPE = HOST_PORT
  VALUE_LIST = ('slack.com', 'www.slack.com', 'api.slack.com', 'wss-primary.slack.com'); 

CREATE OR REPLACE NETWORK RULE SNOWFLAKE_NETWORK_RULE
  MODE = EGRESS
  TYPE = HOST_PORT
  VALUE_LIST = ('*.snowflakecomputing.com');

-- If you're running Snowflake behind a VPN, you'll need to add the IPs here and attach the rule to you user policy
-- or create a rule that allows all traffic, add that to a policy and test with all traffic for now.
CREATE OR REPLACE NETWORK RULE ALLOW_ALL_IPS
    MODE = EGRESS
    TYPE = HOST_PORT
    VALUE_LIST = ('0.0.0.0/0')
    COMMENT = 'Network rule for Snowflake Cortex Agent API access';

CREATE OR REPLACE NETWORK POLICY
    ALLOWED_NETWORK_RULE_LIST = ('ALLOW_ALL_IPS');

ALTER USER <username> SET NETWORK_POLICY = ALLOW_ALL_IPS;


CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION SLACK_ACCESS_INTEGRATION
  ALLOWED_NETWORK_RULES = (SLACK_NETWORK_RULE, SNOWFLAKE_NETWORK_RULE)
  ENABLED = TRUE;

-- 4. Create Compute Pool (The VM that runs your container)
CREATE COMPUTE POOL IF NOT EXISTS CORTEX_POOL
  MIN_NODES = 1
  MAX_NODES = 1
  INSTANCE_FAMILY = CPU_X64_XS;

-- Wait for the pool to be ACTIVE
SHOW COMPUTE POOLS;

-- 5. Create the Service
-- Make sure you have pushed the docker image before running this!
CREATE SERVICE CORTEX_SLACK_BOT_SERVICE
  IN COMPUTE POOL CORTEX_APP_POOL
  EXTERNAL_ACCESS_INTEGRATIONS = (SLACK_ACCESS_INTEGRATION)
  FROM SPECIFICATION $$
    spec:
      containers:
        - name: cortex-slack-bot
          image: /<database-name>/apps/<image-repo-name>/cortex_slack_bot:latest
          env:
            # Update these values with your actual credentials
            ACCOUNT: "<account-identifier>"
            HOST: "<account-identifier>.snowflakecomputing.com"
            DEMO_USER: "<username>"
            DEMO_USER_ROLE: "<role-name>"
            WAREHOUSE: "<warehouse>"
            AGENT_ENDPOINT: "https://<account-identifier>.snowflakecomputing.com/api/v2/databases/<database-name>/schemas/<schema-name>/agents/<agent-name>:run"
            SLACK_APP_TOKEN: "xapp-..."
            SLACK_BOT_TOKEN: "xoxb-..."
            PAT: "<ProgrammicAccessToken>"
          volumeMounts:
            - name: app-storage
              mountPath: /app/data
      volumes:
        - name: app-storage
          source: local
  $$;

-- 6. Check status
SELECT SYSTEM$GET_SERVICE_STATUS('CORTEX_SLACK_BOT_SERVICE');
SELECT SYSTEM$GET_SERVICE_LOGS('CORTEX_SLACK_BOT_SERVICE', 0, 'cortex-slack-bot');
```

### Steps to Deploy

1.  **Build the Docker Image**:
    Navigate to your folder in your terminal:
    ```bash
    docker build --platform linux/amd64 -t cortex_slack_bot:latest .
    ```
    *(Note: `--platform linux/amd64` is crucial because SPCS runs on Linux/AMD64. If you build on a Mac M1/M2/M3 without this, it will crash.)*

2.  **Login to Snowflake Registry**:
    ```bash
    docker login <your_registry_url> -u <username>
    ```

3.  **Tag and Push**:
    ```bash
    docker tag cortex_slack_bot:latest <your_registry_url>/cortex_slack_bot:latest
    docker push <your_registry_url>/cortex_slack_bot:latest
    ```

4.  **Run the SQL**:
    Execute step 5 in the SQL script to spin up the service.

### Troubleshooting Network Access

Since you are using **Socket Mode**, the bot initiates a WebSocket connection to Slack (`wss://...`).
If the bot starts but immediately crashes or hangs, check the logs:
```sql
SELECT SYSTEM$GET_SERVICE_LOGS('CORTEX_SLACK_BOT_SERVICE', 0, 'cortex-slack-bot');