#!/usr/bin/env python3
#
# Copyright (c) 2024, Honda Research Institute Europe GmbH
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#
# 1. Redistributions of source code must retain the above copyright notice,
#  this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright
#  notice, this list of conditions and the following disclaimer in the
#  documentation and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its
#  contributors may be used to endorse or promote products derived from
#  this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS
# IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
# THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
# PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
# CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
# EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
# PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
# NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
import importlib
import inspect
import json
import logging
import os.path

from typing import (
    Literal,
    Union,
)

import openai

from function_analyzer import FunctionAnalyzer
import gpt_config

# import tools
tool_module = importlib.import_module(gpt_config.tool_module)
TOOLS = {n: f for n, f in inspect.getmembers(tool_module) if inspect.isfunction(f)}


class ToolAgent:
    """
    LLM-backed agent with access to functions
    """

    def __init__(
        self,
    ) -> None:
        # llm settings
        if not os.path.isfile(os.getenv("OPENAI_API_KEY")):
            openai.api_key_path = None
        openai.api_key = os.getenv("OPENAI_API_KEY")
        self.openai_client = openai.OpenAI()
        self.model = gpt_config.model_name
        self.temperature = gpt_config.temperature

        self.sim = tool_module.SIMULATION

        # Character and tools
        self.character: str = gpt_config.system_prompt
        self.function_resolver = TOOLS
        self.function_analyzer = FunctionAnalyzer()
        self.tools = [
            self.function_analyzer.analyze_function(function_)
            for function_ in TOOLS.values()
        ]

    def _query_llm(
        self, messages, tool_choice: Union[Literal["none", "auto"]] = "auto"
    ):
        response = ""
        try:
            response = self.openai_client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                messages=messages,
                tools=self.tools,
                tool_choice=tool_choice,
            )
            logging.info(response)
        except openai.OpenAIError as e:
            logging.error(f"❌ OpenAI error: {e}")
            pass
        return response

    def plan_with_functions(self, text_input):
        messages = [
            {"role": "system", "content": self.character},
            {"role": "user", "content": text_input},
        ]
        response = self._query_llm(messages)
        messages.append(response.choices[0].message)

        # run with function calls as long as necessary
        while response.choices[0].message.tool_calls:
            tool_calls = response.choices[0].message.tool_calls
            gaze_ = [tc for tc in tool_calls if tc.function.name == "gaze"]
            speech_ = [tc for tc in tool_calls if tc.function.name == "speak"]
            actions_ = [
                tc for tc in tool_calls if tc not in gaze_ and tc not in speech_
            ]
            for tcs in [gaze_, speech_, actions_]:
                if not tcs:
                    continue
                for tc in tcs:
                    function_call = tc.function
                    # invoke functions
                    func = function_call.name
                    fn_args = json.loads(function_call.arguments)
                    print(
                        "🤖🔧 GPT response is function call: "
                        + func
                        + "("
                        + str(fn_args)
                        + ")"
                    )
                    fcn = self.function_resolver[func]
                    fn_res = fcn(**fn_args)
                    print("🔧 Function result is: " + fn_res)

                    # query with function result
                    messages.append(
                        {
                            "role": "tool",
                            "name": func,
                            "content": fn_res,
                            "tool_call_id": tc.id,
                        }
                    )
            response = self._query_llm(messages)
            messages.append(response.choices[0].message)

        print("🤖💭 FINAL RESPONSE: " + response.choices[0].message.content)

    def set_busy(self, agent: str, thing: str):
        self.sim.execute(f"magic_get {thing} {agent}")
        # TODO: return success message from sim
        print(f"📝 Set {agent} to busy with {thing}.")


if __name__ == "__main__":
    agent = ToolAgent()
    agent.sim.run()
    # examples
    # "You are a helpful but really whiny robot."
    # agent.plan_with_functions("Grasp a bottle")
    # agent.plan_with_functions("Tell me a joke")

    # You are a helpful robot. Be very apologetic if you cannot do what I ask.
    # agent.plan_with_functions("Grasp a bottle and put in on a box")
    # agent.plan_with_functions("You are really shaky. Never grasp anything again!")

    # agent.plan_with_functions("Grasp exactly one bottle and tell me which one you grasped in parallel")
    # agent.tools['get_scene_entities']()
