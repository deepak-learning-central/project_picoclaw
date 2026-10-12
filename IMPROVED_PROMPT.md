# Improved Prompt for Dockerized PicoClaw Setup Project

## Original Prompt Analysis
The original request was vague and lacked structure, making it difficult to determine exact requirements. Key issues:
- Ambiguous phrasing ("setup file", "few commands")
- Unclear problem statement (problem #1 mentioned but not fully explained)
- Missing specifications for desired output format, constraints, and examples
- No clear definition of what constitutes a successful solution

## Improved Prompt

**Role:** You are an expert DevOps engineer specializing in Dockerized application deployment and automated setup systems.

**Context:** 
- User wants to create a minimal project that automates PicoClaw setup using Docker
- Current approach clones PicoClaw source into same directory as setup files, which is undesirable
- User has reviewed Notes.md and README.md from PicoClaw project
- Goal is a portable setup requiring minimal manual intervention on new machines
- Docker-compose based solution preferred

**Task:**
Create a self-contained project structure that enables zero-configuration PicoClaw deployment on any Docker-capable machine. The project should:
1. Contain ONLY Docker orchestration files and automation scripts (no PicoClaw source code)
2. Automatically clone the official PicoClaw repository during setup
3. Build the required "full" Docker image from source (not use pre-built :latest image)
4. Properly configure both config.json and .security.yml with correct nested settings structure
5. Handle file ownership issues that arise from container/host boundary
6. Include interactive setup for API keys/tokens with secure storage
7. Provide clear startup/shutdown instructions

**Constraints:**
- Project must not include PicoClaw source code in its repository
- Must use docker-compose.full.yml for reliable channel support (Discord/Telegram/etc.)
- Setup process should be idempotent where possible
- All secrets must be stored separately from config.json (.security.yml)
- Files must include proper .gitignore rules to prevent accidental secret commits
- Solution must work on Raspberry Pi and x86_64 Linux systems
- Include documentation explaining the nested-settings requirement for channels
- Provide validation steps to confirm proper channel initialization

**Output Format:**
Provide a complete file structure with:
1. Directory layout showing all required files
2. Content of each file with explanatory comments
3. Step-by-step usage instructions for end-users
4. Troubleshooting tips based on known issues from Notes.md
5. Example of expected successful output

**Example Structure:**
```
pico-docker-setup/
├── docker-compose.yml           # Main compose file referencing full build
├── setup.sh                     # Automated setup script (based on original)
├── README.md                    # User-friendly instructions
├── .gitignore                   # Prevents committing secrets
└── scripts/
    ├── initialize.sh            # First-time setup helper
    └── update.sh                # Update PicoClaw source and rebuild
```

**Key Requirements to Address:**
1. Use `docker-compose.full.yml` specifically (not regular compose file)
2. Build `picoclaw-gateway` service from source
3. Mount both `config.json` and `.security.yml` with correct paths
4. Handle Telegram (flat) vs Discord/DingTalk (nested) settings properly
5. Fix ownership with recursive chown after container operations
6. Include secure credential handling instructions
7. Provide clear verification steps for channel initialization

**Success Criteria:**
- On a fresh machine with Docker installed, running `./setup.sh` should:
  1. Clone PicoClaw repository
  2. Build required Docker images
  3. Guide user through API key/token configuration
  4. Start all services successfully
  5. Confirm channels are properly initialized (check logs)
  6. Require no manual Docker command intervention after setup begins