"""Goal Generator Node - LLM generates goal_formula from TTL environment data."""

import uuid
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
import sys
from pathlib import Path

# Add ontology_server to path for config access
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "ontology_server"))

from ..state import OverallState
from ..prompts import scenario_generator_prompt

# Import TTL reader - needs path setup in ttl_reader module
from ..tools.ttl_reader import get_complete_environment_info


def goal_generator(state: OverallState, config: RunnableConfig) -> dict:
    """
    Generate a PDDL goal formula using LLM based on TTL environment data.
    
    Workflow:
    1. Read TTL files for active environment
    2. Generate summary of available objects, locations, affordances
    3. Use LLM to create realistic goal formula
    4. Extract goal_formula and store in state (validation will happen next)
    
    Returns:
        State updates with goal_formula in user_instruction
    """
    try:
        # Track generation attempts to prevent infinite loops
        generation_attempts = state.get("generation_attempts", 0) + 1
        max_attempts = 3
        
        if generation_attempts > max_attempts:
            return {
                "messages": [AIMessage(
                    content=f"ERROR: Maximum goal generation attempts ({max_attempts}) reached. "
                           f"Could not generate a valid goal formula after multiple attempts with feedback."
                )]
            }
        
        # Get complete environment information (spaces, artifacts, PDDL predicates)
        environment_info = get_complete_environment_info()
        
        # Check if there are validation errors from previous attempt (feedback loop)
        validation_errors = state.get("validation_errors")
        validation_feedback = ""
        
        if validation_errors:
            validation_feedback = "\n\n## PREVIOUS VALIDATION ERRORS (MUST FIX):\n\n"
            validation_feedback += "\n".join(f"- {err}" for err in validation_errors)
            validation_feedback += f"\n\n**IMPORTANT:** The previous goal formula had validation errors (attempt {generation_attempts - 1}/{max_attempts}). "
            validation_feedback += "Please generate a NEW goal formula that:\n"
            validation_feedback += "1. Avoids all the errors listed above\n"
            validation_feedback += "2. Follows all logical consistency requirements\n"
            validation_feedback += "3. Uses objects with known locations and correct affordances\n"
            validation_feedback += "4. Does NOT repeat the same logical contradictions\n\n"
        
        # Prepare prompt for LLM
        human_message = "Generate a PDDL goal formula for a robot task based on this environment:\n\n{environment_data}"
        if validation_feedback:
            human_message += validation_feedback
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", scenario_generator_prompt),
            ("human", human_message)
        ])
        
        # Initialize LLM
        llm = ChatOpenAI(model="gpt-4o", temperature=0.7)
        
        # Generate goal formula
        chain = prompt | llm
        response = chain.invoke({"environment_data": environment_info})
        
        # Extract goal formula from LLM response
        goal_formula = response.content.strip()
        
        # Remove markdown code blocks if present
        if goal_formula.startswith("```"):
            lines = goal_formula.split("\n")
            goal_formula = "\n".join(lines[1:-1]) if len(lines) > 2 else goal_formula
            goal_formula = goal_formula.strip()
        
        # Remove any surrounding quotes
        if (goal_formula.startswith('"') and goal_formula.endswith('"')) or \
           (goal_formula.startswith("'") and goal_formula.endswith("'")):
            goal_formula = goal_formula[1:-1]
        
        goal_formula = goal_formula.strip()
        
        # Validate that we got a goal formula
        if not goal_formula or not goal_formula.startswith("("):
            return {
                "messages": [AIMessage(
                    content=f"ERROR: LLM failed to generate valid PDDL goal formula. Response: {response.content}"
                )]
            }
        
        # Store goal formula in state for validation
        return {
            "messages": [AIMessage(
                content=f"Generated goal formula (attempt {generation_attempts}): {goal_formula}\n\nEnvironment info loaded: {len(environment_info)} characters"
            )],
            "user_instruction": goal_formula,  # Store for validation
            "generation_attempts": generation_attempts
        }
        
    except Exception as e:
        error_msg = f"ERROR in goal_generator: {type(e).__name__}: {str(e)}"
        return {
            "messages": [AIMessage(content=error_msg)]
        }

