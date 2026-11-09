from typing import TypedDict
from pydantic import BaseModel
from langgraph.graph import StateGraph, START, END
from fastapi import HTTPException
from app.mcp.client_manager import invoke


class AgentResult(BaseModel):
    agent: str
    tool: str
    status: str
    explanation: str


class WorkflowState(TypedDict, total=False):
    workflow_id: str
    user_id: str
    organization_id: str
    requested_operation: str
    agent_name: str
    approved_tool_scope: list[str]
    execution_status: str
    tool_calls: list[str]
    execution_result: dict
    explanation: dict


async def run(user, request, workflow_id):
    # Authenticated identity is closed over by trusted code, never supplied by a model.
    routes = {'customer': ('Customer Service Agent', 'get_customer_profile'),
              'balance': ('Account Information Agent', 'get_account_balance'),
              'payment': ('Payment Workflow Agent', 'prepare_payment_instruction')}

    def classify(state):
        agent, tool = routes[request.operation]
        return {'agent_name': agent, 'approved_tool_scope': [tool], 'execution_status': 'CLASSIFIED'}

    async def specialist(state):
        if request.operation == 'customer' and request.customer_id:
            args = {'customer_id': request.customer_id}
        elif request.operation == 'balance' and request.account_id:
            args = {'account_id': request.account_id}
        elif request.operation == 'payment' and request.payment:
            args = {'request': request.payment.model_dump(mode='json')}
        else:
            raise HTTPException(422, 'Required workflow fields absent')
        tool = state['approved_tool_scope'][0]
        output = await invoke(user, tool, args)
        return {'tool_calls': [tool], 'execution_result': output, 'execution_status': 'COMPLETED'}

    def explain(state):
        result = AgentResult(agent=state['agent_name'], tool=state['tool_calls'][0], status='COMPLETED',
                             explanation='Deterministic mock routing completed an authorized MCP operation. Payment proposals require separate human approval.')
        return {'explanation': result.model_dump()}

    graph = StateGraph(WorkflowState)
    graph.add_node('classify', classify)
    graph.add_node('specialist', specialist)
    graph.add_node('explain', explain)
    graph.add_edge(START, 'classify')
    graph.add_edge('classify', 'specialist')
    graph.add_edge('specialist', 'explain')
    graph.add_edge('explain', END)
    return await graph.compile().ainvoke({'workflow_id': workflow_id, 'user_id': user.id,
                                         'organization_id': user.org_id, 'requested_operation': request.operation})
