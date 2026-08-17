# Product Questions

## Q1. What broke?

The biggest issues I ran into were around the gap between the ideal workflow and what can actually be verified in a local development environment.

One example was the local PostgreSQL setup. The database container was running, but the application tables were not automatically created, which initially caused API requests to fail. I had to trace the problem through the database configuration and initialization flow rather than assuming that starting PostgreSQL was enough.

Another limitation was the SuperDocs integration. I implemented the SuperDocs REST client and kept it stub-first so the system could be tested without depending on a real API key or a live SuperDocs environment. Because of that, I could verify the integration structure and application behavior, but I did not want to falsely claim that the complete cloud integration had been production-verified.

I also learned that document validation is much harder when the actual document contents are not parsed. In the current implementation, document records and metadata are available, but things such as signatures, dates, declarations, or sections inside a PDF cannot automatically be treated as verified facts.

The main lesson for me was that a good validator should be honest about what it knows. If the required evidence is missing, the system should return insufficient_evidence rather than pretending the requirement passed.

## Q2. If you were running SuperDocs, what ONE number would you watch every morning, and why?

I would choose this because it connects the product directly to the user's actual experience.

A product can have many users and many documents being uploaded, but that does not necessarily mean the product is working well. If users regularly get stuck during document processing, editing, approval, or export, then the product is creating work instead of removing it.

I would track this number over time and break it down by workflow stage when it decreases. That would help identify whether the problem is related to uploading, AI processing, editing, approval, export, or an external integration.

## Q3. Name FIVE features you would build next, in order.

1. Reliable document understanding

I would first improve the ability to actually understand uploaded document contents rather than relying primarily on metadata.

The system should be able to identify things such as sections, dates, signatures, declarations, tables, and other important facts while preserving their source locations.

Why first: This would make the validation system much more useful and would reduce the amount of insufficient_evidence caused by information that exists inside documents but is not currently extracted.

1. Better evidence and citations

Every finding should be able to show exactly where the supporting evidence came from.

For example:

Document → Page → Section → Extracted text → Rule → Finding

Why second: Trust is extremely important for an AI document product. A user should be able to understand why the system reached a conclusion instead of simply trusting an AI-generated answer.

1. Human review workspace

I would build a better review experience around conflicts, low-confidence findings, and required approvals.

The reviewer should be able to see:

The finding
The rule
Evidence
The affected document
The proposed action
Approve/reject controls

Why third: Human review is already part of the workflow, so giving reviewers a clear interface would make the system much more practical.

1. Production-grade SuperDocs integration

I would replace the stub-first integration with a fully verified production integration, including authentication, retries, error handling, rate limits, and observability.

Why fourth: The integration is an important part of the overall workflow, but I would build it after making the core document understanding and evidence model reliable.

1. Operational monitoring and analytics

I would add dashboards for workflow success rate, failures, processing time, human-review rate, validation results, and integration errors.

Why fifth: Once the core workflow is reliable, these metrics would help the team understand how customers are actually using the product and where the system needs improvement.

What I would deprioritize

I would deprioritize building a large UI before the underlying document understanding and evidence model are reliable.

A beautiful interface cannot compensate for a system that cannot confidently explain where its conclusions came from.

I would also fix immediate reliability issues before adding more AI features.

## Q4. How would you make SuperDocs' day-to-day development and GTM operations run themselves?

I would build SuperDocs around a set of specialized AI agents rather than one large agent trying to do everything.

Development loop

One group of agents could continuously:

Observe → Detect → Propose → Test → Review → Deploy

For example:

A monitoring agent detects failing tests or production errors.
A debugging agent investigates the likely cause.
A coding agent proposes a change.
A testing agent creates or runs tests.
A review agent checks the change against project rules.
A human approves important changes before deployment.
Product loop

Another set of agents could analyse:

User feedback
Support conversations
Failed workflows
Frequently requested features
Document-processing failures
User drop-off points

They could turn these signals into a ranked list of product improvements.

GTM loop

For go-to-market operations, agents could help with:

Lead research
Account qualification
Preparing personalized outreach
Tracking responses
Preparing customer summaries
Identifying common customer problems
Generating sales enablement material

But I would keep sending important external communication behind human approval initially.

Guardrails

I would not allow agents to operate without boundaries.

Important actions would have:

Permission limits
Audit logs
Structured outputs
Automated tests
Human approval
Rate limits
Rollback mechanisms
Clear ownership

For example, an agent could propose a production code change, but it should not automatically deploy a risky database migration without human approval.

Where humans stay involved

I would keep humans responsible for:

High-impact product decisions
Production changes with significant risk
Customer commitments
Financial decisions
Regulatory decisions
Security/privacy decisions
Approving major AI-generated changes

The goal would not be:

“Remove humans.”

It would be:

“Remove repetitive work so humans spend their time making decisions that actually require judgment.”

What I think would break first

The first thing I would worry about is agent reliability and coordination.

When many agents are allowed to create and modify things automatically, small mistakes can compound. An agent might misunderstand a requirement, another agent might build on that incorrect assumption, and the final result could look reasonable while being wrong.

So I would start with a small number of well-defined loops, strong observability, and human checkpoints, and only increase autonomy after the system demonstrates that it can operate safely.