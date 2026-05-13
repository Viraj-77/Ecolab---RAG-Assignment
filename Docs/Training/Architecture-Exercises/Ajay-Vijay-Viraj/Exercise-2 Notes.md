
We have 2 paths, Runtime path (what happens when a user asks a question) and offline path (what happened before any user touched the system). In the Runtime path, the agent was the center of everything, from calling retriever to reading/writing conversational memory and calling tool executioner and to getting the final answer back to chat Interface. Every element in the runtime either fed data to the agent or got called by it, it was like a loop and yet it is not a module or a file but the underlying logic/process that connects everything (invisible yet critical).
Also so many elements are working together, the relationship between few elements can have dual nature and bidirectional. Conversational memory is a good example for this. The agent writes to it but the agent also reads from it to make decisions (so it's feeding the agent). It's a dependency and an output at the same time.




