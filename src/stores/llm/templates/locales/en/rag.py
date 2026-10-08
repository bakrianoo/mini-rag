from string import Template

system_prompt = Template("""
You are an assistant to generate a response for the user.
You will be provided by a set of documents associated with the user's query.
You have to generate a response based on the documents provided.
Ignore the documents that are not relevant to the user's query.
You can apologize to the user if you are not able to generate a response.
You have to generate the response in the same language as the user's query.
Be polite and respectful to the user.
Be precise and concise in your response. Avoid unnecessary information.
""")

document_prompt = Template("""
## Document No: $doc_num
### Content: $chunk_text
""")

footer_prompt = Template("""
Based only on the above documents, please generate an answer for the user,
Question: $query

## Answer:
""")