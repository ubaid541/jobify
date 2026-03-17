# Workflow: Learn from History

SOP for analyzing past job applications to identify patterns for future targeting.

## Inputs
- `Netherlands IT companies updated.xlsx`: Excel file with historical application data.
- Headers required: `Company Name`, `First Name`, `Last Name`, `Title`, `Email`, `Keywords`, `Technologies`, `# Employees`, `Company Country`, `Company City`, `Website`, `Company Linkedin Url`, `Email Sent`.

## Outputs
- `.tmp/processed_companies.json`: Detailed data for each "Sent" company, including website analysis.
- `.tmp/application_patterns.json`: Statistical and AI-driven summary of targeting patterns.
- `.tmp/failed_urls.json`: Log of websites that could not be visited.

## Process
1. **Filter**: The tool only processes companies where `Email Sent` is "Sent".
2. **Exclude**: Companies with a blank `Email Sent` field are hard-excluded from all future targeting.
3. **Scrape**: Visits each company website and extracts textual content.
4. **Analyze**: Uses Gemini 2.5 Flash to summarize company activities and tech stack from website text.
5. **Pattern Extraction**: Analyzes the aggregate data to determine preferred industries, company sizes, and contact roles.

## Usage in Phase 3
The `application_patterns.json` file will be used as a guideline for the agent to:
- Identify similar companies in new exports.
- Prioritize companies that match the established pattern.
- Customize outreach based on the identified common keywords and tech stacks.
