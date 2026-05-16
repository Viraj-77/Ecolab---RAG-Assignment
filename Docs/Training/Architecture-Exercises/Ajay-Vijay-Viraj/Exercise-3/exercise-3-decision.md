
Variant A i.e. Azure Native hand build is the clear winner here, organizations have strict compliance requirements which Azure can follow and is provable. Azure Variant also has more freedom to modify the system, add new features, tools and can be scaled up based on the requirements/demands. The high cost fot Variant A is justified by all this, whereas Variant B has the upper hand of speed of setting up and giving the service.
### Trade Offs Axes:

|              Axis              | Variant A — Azure Native Hand Build | Variant B — Copilot Studio |
| :----------------------------: | :---------------------------------: | :------------------------: |
|     **Time-to-first-user**     |               Medium                |            Low             |
|    **Permission fidelity**     |                High                 |            High            |
|       **Data residency**       |                High                 |            High            |
| **Cost per active user/month** |               Medium                |           Medium           |
|       **Extensibility**        |                High                 |            Low             |
|       **Vendor lock-in**       |                High                 |            Low             |
|       **Observability**        |               Medium                |            High            |
|      **Skills required**       |               Medium                |            Low             |

### Twists:

1. *"Legal now says no document content may leave the EU tenant."* — does your answer change?
   Variant A survives, we can control all azure resource region and is provable. Whereas Variant B might or might not survive because microsoft graph is controlled by microsoft, hard to guarantee.
2. Rollout expands from 500 to 40 000 users."* — where does your design break first?
   Azure OpenAI component will break cause Rate limit will hit. Whereas in Variant B we have licenses for every user, so without licenses, users cant be added to the system.
3. *"A BU wants to extend the bot with a custom tool that calls their internal API."* — is your design open or closed to this?
   Variant A's design is full open cause the entire system has our code so we have the freedom to modify it according to the business needs. Not possible in Variant B.
4. *"Users are asking multi-document comparison questions."* — does RAG still work, or do you need agentic retrieval?
   In Varinat A, modifications to the system like multiple retrieval steps can make it work, but in Variant B it wont work.
5. *"Budget cap: €5 000/month all-in."* — which variant survives?
   Variant A survives at a low/medium scale, openAI tokens would cost us, but where as in Variant B we need to buy license for every user i.e. $30 per user, even if we have 200 users, cost will exceed $5000