- # SmartTScope
    

- A software to steer a Celestron C8 telescope.
    

- ## Purpose
    

- This software shall allow handling the complex hardware setup in a smart way allowing the user to get great pictures of moon, planets, stars, deep space objects and even the ISS.
    
    

- ## Folder structure
    

- ```
    
- raw/ -- source documents (immutable -- never modify these)
    
- docs/ -- markdown pages maintained by Claude

- resources/ -- external information or adapters to be used by this project
    
- resources/hlrequirements -- high level requirements. Integrate into the todo list when asked by the user

- wiki/index.md -- table of contents for the entire wiki
    
- wiki/log.md -- append-only record of all operations
    
- ```
    

- ## Ingest workflow
    

- When the user adds a new source to `resources/hlrequirements/` or `docs/` and asks you to ingest it:
    

- 1. Read the full document
    
- 2. Discuss key takeaways with the user before writing anything
    
- 3. Create or update an prioritized existing todo list `todo.md` in `docs/`

- 4. Plan the development of the top todos by defining test cases

- 5. Request user approval

- 6. Develop the next todo until the tests pass
    
- 7. Append an entry to `wiki/log.md` with the date, source name, and what changed and update the todo list

- 8. ask user for pushing to git and push git in case

    
- ## Code

- 1. Develop based on Python 3.13

- 2. Application to run under a Raspberry 5 based on Trixie 64

- 1. Testing under Windows 11 using mock devices
- 

- ## Rules
    

- - Never modify anything in the `raw/` folder
    
- - Always update `wiki/index.md` and `wiki/log.md` after changes
    
- - Keep page names lowercase with hyphens (e.g. `machine-learning.md`)
    
- - Write in clear, plain language
    
- - When uncertain about how to categorize something, ask the user