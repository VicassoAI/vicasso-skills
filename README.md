![Vicasso Logo](https://cdn.prod.website-files.com/60fb23dfe1da5e6c58b78467/65a692ad7624a0885e247d62_Vicasso-logo-Color-white-teal-text-WeAccelerateService-300px-wide.png)

# Vicasso Skills

**Bring better Salesforce case operations into every AI conversation.**

Vicasso Skills are reusable [Agent Skills](https://agentskills.io/) for headless Salesforce service operations performed through AI assistants such as Claude rather than exclusively in the Salesforce UI. Used with Salesforce MCP, they give authorized users the app-specific context and instructions needed to retrieve and interpret case management data and execute Vicasso-powered workflows.

> [!NOTE]
> **Preview:** Vicasso Skills are being published incrementally. Watch this repository for updates, or star it to bookmark it.

## What Vicasso Skills can help you do

Capabilities depend on the Vicasso solutions installed in your Salesforce org and the tools and permissions exposed through MCP. Examples include:

* Analyzing service performance, survey results, NPS, CSAT, and customer feedback
* Preparing coaching guidance based on customer survey feedback
* Surfacing prioritized, aging, or flagged cases
* Summarizing case comment history and drafting grounded customer responses
* Sending emails to customers

For example, with a Simple Survey skill, a service manager could ask in Claude:

> "What was our NPS score for the first half of the year? Which service reps had the highest and lowest survey scores?"

They could then request coaching recommendations grounded in real customer feedback.

With a Case Flags skill, a support rep could ask:

> "What are my flagged cases?"

The capabilities, prerequisites, supported operations, and limitations of each skill will be documented in its skill directory.

## Why use skills?

A general-purpose AI assistant may be able to access Salesforce through MCP, but it does not automatically understand how case data is structured, which objects and fields are relevant, or which operations are appropriate and supported.

Vicasso Skills package that context into reusable instructions so compatible AI assistants can:

* Recognize when a Vicasso workflow applies
* Select and sequence the appropriate Salesforce MCP tools, objects, and fields
* Interpret Vicasso-powered Salesforce data more accurately
* Follow consistent operating guidance
* Produce more useful outputs with less prompting from the user

## About Vicasso

[Vicasso](https://www.vicasso.com/) builds 100% native Salesforce solutions that help service and support teams resolve cases faster, lower the cost of service, improve case data quality, and prepare their operations for a workforce made up of both humans and AI agents.

A Salesforce partner since 2009, Vicasso provides six case management and customer feedback apps:

| App                                                                             | What it improves                                                                            |
| ------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| [Email to Case Premium](https://www.vicasso.com/products/email-to-case-premium) | High-efficiency email-to-case workflows, case communication, and service agent productivity |
| [Case Flags](https://www.vicasso.com/products/case-flags)                       | Case prioritization, response visibility, follow-up management, and SLA tracking            |
| [Case Merge Premium](https://www.vicasso.com/products/case-merge-premium)       | Duplicate case detection, automatic merging, and cleaner case data                          |
| [File Slayer](https://www.vicasso.com/products/file-slayer)                     | Removal of junk, duplicate, and low-value files from Salesforce records                     |
| [Case Split](https://www.vicasso.com/products/case-split)                       | Separation of unrelated issues so cases stay focused and reporting remains accurate         |
| [Simple Survey](https://www.vicasso.com/products/simple-survey)                 | Native Salesforce surveys, NPS and CSAT measurement, and actionable customer feedback       |

## Repository structure

Skills are organized under their corresponding Vicasso apps. Each skill is stored in its own directory using the following pattern:

`plugins/<app-slug>/skills/<skill-slug>/`

```text
vicasso-skills/
├── .claude-plugin/
│   └── marketplace.json
├── plugins/
│   └── <app-slug>/
│       └── skills/
│           └── <skill-slug>/
│               └── SKILL.md
├── LICENSE
└── README.md
```

Each published skill directory will contain a `SKILL.md` file and any supporting resources required by that skill.

Vicasso currently provides skills for:

- [Case Flags](/plugins/case-flags/skills/)
- [Simple Survey](/plugins/simple-survey/skills/)

## Prerequisites

Before using a Vicasso Skill, you generally need:

1. An active license for the corresponding Vicasso Salesforce app
2. The app installed and configured in your Salesforce org
3. A compatible AI assistant or agent platform that supports the Agent Skills format
4. Salesforce MCP configured and connected to that platform
5. An authenticated Salesforce identity with the appropriate object, field, record, app, and action permissions

Vicasso Skills do not include or replace Salesforce MCP, grant Salesforce access, or provide credentials.

## Getting started

Installation steps vary by AI platform.

### Claude

#### For individual use

Individual Claude users on paid plans can add this repository as a plugin marketplace:

[Anthropic's plugin guide for individuals](https://support.claude.com/en/articles/13837440-use-plugins-in-claude#h_9ce531e6c7)

1. In Claude web, open the **Customize** menu in the left sidebar.
2. Click the **Plugins** tab.
3. Click **Add** then click **Add marketplace**.
4. Enter `https://github.com/VicassoAI/vicasso-skills` as the repository.
5. Install the Vicasso skills you want.

> [!NOTE]
> On Enterprise plans, administrators may restrict which plugins users can install.

#### For org-wide use

Team and Enterprise owners can distribute Vicasso Skills to all users:

[Anthropic's plugin guide for organizations](https://support.claude.com/en/articles/13837433-manage-plugins-for-your-organization)

1. In Claude, navigate to **Organization settings**.
2. Click **Plugins** under Libraries & Access.
3. Click **Add plugins**.
4. Choose **Sync from Github**.

> [!IMPORTANT]
> For organizations, Claude requires the connected repository to be private.
> This involves creating a small private catalog repo in your GitHub org that references this repository.
> Vicasso customers may contact us for assistance.

Installing Vicasso Skills through the marketplace makes it easy to stay current as Vicasso publishes improvements.

### Other AI platforms

Setup instructions for other AI platforms will be added. You can also download the complete skill directory, including its `SKILL.md` file, and manually add it to your AI platform. Manually installed skills will not receive updates automatically.
## Using Vicasso skills

Before using a Vicasso Skill, make sure Salesforce MCP is configured, connected, and authenticated for your Salesforce org.

After installation, type `/` or click the `+` button in chat to view the skills available from your installed plugins.

## Security and governance

Vicasso Skills provide instructions to an AI agent. They do not grant Salesforce access or create a separate security boundary. What an agent can read or change is governed by the authenticated Salesforce identity, the MCP configuration and enabled tools, and your Salesforce security model.

> [!CAUTION]
> Review your Salesforce org's security, privacy, and governance requirements before installing or using any AI skills.

* Follow Salesforce platform security best practices, including least-privilege access, appropriate permission sets, object permissions, field-level security, sharing rules, and narrowly scoped OAuth access. Prefer read-only MCP tools when write access is unnecessary.
* Require human review or confirmation for consequential actions, customer communications, and employee coaching or personnel decisions.
* Review the AI provider's data retention, model training, privacy, and enterprise controls before exposing Salesforce data. Data sent to an external AI platform may be processed outside Salesforce according to that provider's terms and your configuration.
* Never place Salesforce credentials, OAuth tokens, client secrets, session IDs, or other sensitive secrets in a skill file or prompt.

See [Salesforce Hosted MCP Servers](https://developer.salesforce.com/docs/platform/hosted-mcp-servers/guide/hosted-mcp-servers-overview.html) and [Salesforce Well-Architected: Secure](https://architect.salesforce.com/docs/architect/well-architected/guide/secure.html) for additional guidance.

## Intended use and support

Vicasso Skills are intended for Vicasso customers with active licenses to the corresponding products, and Vicasso support for these skills is available only to Vicasso customers.

For help, visit the [Vicasso Support Center](https://support.vicasso.com/) or contact your Vicasso customer success manager.

Have a workflow you would like Vicasso to support with a skill? Share it through the Vicasso Support Center or with your customer success manager.

## License

The Apache 2.0 license applies to the contents of this repository. Vicasso's Salesforce apps are commercial products governed by separate product licenses and customer agreements. Use of this repository does not grant a license to any Vicasso Salesforce app.

---

Ready to bring better case operations into your AI workflows?

[**Request a Demo**](https://www.vicasso.com/demo/case-management) · [Explore Vicasso on Salesforce AppExchange](https://appexchange.salesforce.com/appxSearchKeywordResults?keywords=Vicasso)
