from brewparse import parse_program
from intbase import ErrorType, InterpreterBase

class Interpreter(InterpreterBase):
    def __init__(self, console_output=True, inp=None, trace_output=False):
        super().__init__(console_output, inp)   # call InterpreterBase's constructor
    
    def interpret_statement(self, statement):
        if self.trace_output == True:
            print(statement)

    #main run function
    def run(self,program):
        ast = parse_program(program)
        self.variable_name_to_value = {}
        main_func_node = ast.dict["functions"][0]
        if(main_func_node.dict["name"] != "main"):
            super().error(
                ErrorType.NAME_ERROR,
                f"main function has not been defined",
                )
        self.run_func(main_func_node)    

    def run_func(self,func_node):
        for statement_node in func_node.dict["statements"]:
            self.run_statement(statement_node)         
    


    def run_statement(self,statement_node):
        if(self.is_assignment(statement_node)):
            self.do_assignment(statement_node)
        elif(self.is_definition(statement_node)):
            self.do_definition(statement_node)
        elif(self.is_func_call(statement_node)):
            arguments = statement_node.dict["args"]
            if(statement_node.dict["name"] == "print"):
                to_be_printed = ""
                for i in arguments:
                    if(type(i) == str):
                        to_be_printed += i
                    else:
                        to_be_printed += str(self.evaluate_expression(i))
                super().output(to_be_printed)
            elif(statement_node.dict["name"] == "inputi"):
                if(len(arguments) > 1):
                    super().error(
                        ErrorType.NAME_ERROR,
                        "Inputi does not take more than one more argument"
                    )
                elif(len(arguments) == 1):
                    super().output(str(self.evaluate_expression(arguments[0])))
                int(super().get_input()) #Does nothing effectively as we don't store input, but it is here
            else: #unknown function
                super().error(
                ErrorType.NAME_ERROR,
            f"Unknown function call",
            )


    
    def do_assignment(self, statement_node):
        var_name = statement_node.dict["name"] #check to see if the variable we want to assign to is defined
        if(var_name not in self.variable_name_to_value):
            super().error(
                ErrorType.NAME_ERROR,
            f"Variable {var_name} has not been defined",
            )
        source_node = statement_node.dict["expression"]
        value = self.evaluate_expression(source_node)
        self.variable_name_to_value[var_name] = value
            
    def evaluate_expression(self,expression_node):
        if(self.is_value_node(expression_node)):
            return expression_node.dict["val"]
        elif(self.is_variable_node(expression_node)):
            if(expression_node.dict["name"] not in self.variable_name_to_value):
                super().error(
                ErrorType.NAME_ERROR,
                f"Variable {expression_node.dict['name']} has not been defined",
                )
            return self.variable_name_to_value[expression_node.dict["name"]] 
        elif(self.is_is_binary_operator(expression_node)):
            leftArg = self.evaluate_expression(expression_node.dict["op1"])
            rightArg = self.evaluate_expression(expression_node.dict["op2"])
            if(type(leftArg) == str or type(rightArg) == str):
                super().error(
                ErrorType.TYPE_ERROR,
                f"You cannot do binary operations with strings",
                )
            if(expression_node.elem_type == "-"): #need to account for nested expressions
                return leftArg - rightArg
            else: #else in this case is just +
                return leftArg + rightArg
        else: #must be a function call
            arguments = expression_node.dict["args"]
            if(expression_node.dict["name"] == "print"): #barista allows you to print to a variable so...
                to_be_printed = ""
                for i in arguments:
                    if(type(i) == str):
                        to_be_printed += i
                    else:
                        to_be_printed += str(self.evaluate_expression(i))
                super().output(to_be_printed)
            elif(expression_node.dict["name"] == "inputi"):
                #must output arguments, check barista if inputi can take more than one argument: Only one argument, allowed to do variables
                if(len(arguments) > 1):
                    super().error(
                        ErrorType.NAME_ERROR,
                        "Inputi does not take more than one more argument"
                    )
                elif(len(arguments) == 1):
                    super().output(str(self.evaluate_expression(arguments[0])))
                inputiReturn = int(super().get_input()) #if the user inputs anything not an int, a runtime error will occur(follows Barista behavior)
                return inputiReturn
            else:
                super().error(
                ErrorType.NAME_ERROR,
            f"Unknown function call",
            )
                
        
    
    def is_value_node(self,expression_node):
        return expression_node.elem_type == "int" or expression_node.elem_type == "string"

    def is_variable_node(self,expression_node):
        return expression_node.elem_type == "var"

    def is_is_binary_operator(self, expression_node):
        return expression_node.elem_type == "+" or expression_node.elem_type == "-"

        

    def do_definition(self,statement_node):
        name = statement_node.dict["name"]
        if(name in self.variable_name_to_value):
            super().error(
                ErrorType.NAME_ERROR,
                f"Variable {name} defined more than once",
            )
        self.variable_name_to_value[name] = None



    def do_func_call(self, statement_node):
        pass

    #statement type checkers
    def is_definition(self,statement_node):
        try:
            statement_node.dict["var_type"]
            return True
        except:
            return False


    def is_assignment(self,statement_node):
        try:
            statement_node.dict["expression"]
            return True
        except:
            return False

    def is_func_call(self,statement_node):
        try:
            statement_node.dict["args"]
            return True
        except:
            return False



