# Add to spec:
# - printing out a nil value is undefined

from env_v1 import EnvironmentManager
from type_valuev1 import Type, Value, create_value, get_printable
from intbase import InterpreterBase, ErrorType
from brewparse import parse_program

# Main interpreter class
class Interpreter(InterpreterBase):
    # constants
    BIN_OPS = {"+", "-", "*", "/","==","!=","<=",">=",">","<","||","&&"}
    # methods
    def __init__(self, console_output=True, inp=None, trace_output=False):
        super().__init__(console_output, inp)
        self.trace_output = trace_output
        self.__setup_ops()

    # run a program that's provided in a string
    # usese the provided Parser found in brewparse.py to parse the program
    # into an abstract syntax tree (ast)
    def run(self, program):
        ast = parse_program(program)
        self.__set_up_function_table(ast)
        main_func = self.__get_func_by_name("main")
        self.env = [(EnvironmentManager(),False)] #make into a stack, tuple with first being the scope, second boolean representing weather its allowed to go past that scope or not
        self.env[-1][0].create("return", Value(InterpreterBase.NIL_DEF, InterpreterBase.NIL_DEF))
        self.__run_statements(main_func.get("statements"))

    def __set_up_function_table(self, ast):
        self.func_name_to_ast = {}
        for func_def in ast.get("functions"):
            if(func_def.get("name") == "main"):
                self.func_name_to_ast[func_def.get("name")] = func_def #naming scheme exception for main
                continue
            num_args = len(func_def.dict["args"]) #To allow overloading we will have the name of function+(num of args)
            self.func_name_to_ast[func_def.get("name") + "+" + str(num_args)] = func_def

    def __get_func_by_name(self, name):
        if name not in self.func_name_to_ast:
            super().error(ErrorType.NAME_ERROR, f"Function {name} not found")
        return self.func_name_to_ast[name]


    def __run_statements(self, statements):
        # all statements of a function are held in arg3 of the function AST node
        #print(statements)
        for statement in statements:
            if self.trace_output:
                print(statement)
            if (self.env[-1][0].get("return") != None and self.env[-1][0].get("return").value() != InterpreterBase.NIL_DEF):
                break #we have our return statement break out of it
            elif statement.elem_type == InterpreterBase.FCALL_NODE:
                self.__call_func(statement)
            elif statement.elem_type == "=":
                self.__assign(statement)
            elif statement.elem_type == InterpreterBase.VAR_DEF_NODE:
                self.__var_def(statement)
            elif statement.elem_type == InterpreterBase.IF_NODE:
                self.__if_statement(statement)
            elif statement.elem_type == InterpreterBase.FOR_NODE:
                self.__for_statement(statement)
            elif statement.elem_type == InterpreterBase.RETURN_NODE:
                if(statement.dict["expression"] != None):
                    returnVal = self.__eval_expr(statement.dict["expression"])
                else:
                    returnVal = Value(InterpreterBase.NIL_NODE, "RETURNED") #alternate value for nil that means to return
                #set our current environment's return value to what returnVal is
                currentScope = self.env[-1]
                currentIndex = len(self.env) - 1
                while(currentScope[1] == True): #search to find our largest scope where our return is
                    currentIndex -= 1
                    currentScope[0].set("return",returnVal) # keep going back until we hit our last known scope setting our return values accordingly
                    currentScope = self.env[currentIndex] # they might call return in main(), account for this if test case
                currentScope[0].set("return",returnVal) #reached back to our current main scope
                break #after a return we end program execution

    def __if_statement(self, statement):
        condition = self.__eval_expr(statement.dict["condition"])
        if(condition.value() == True):
            self.env.append((EnvironmentManager(),True)) #add another scope to our local environment
            current_return_val = self.env[-2][0].get("return")
            self.env[-1][0].create("return", Value(current_return_val.type(),current_return_val.value())) 
            self.__run_statements(statement.dict["statements"])
            self.env.pop()
        elif(condition.value() == False):
            if(not (statement.dict["else_statements"] is None)): #only run if we actually have else statements
                self.env.append((EnvironmentManager(),True))
                current_return_val = self.env[-2][0].get("return")
                self.env[-1][0].create("return", Value(current_return_val.type(),current_return_val.value())) 
                self.__run_statements(statement.dict["else_statements"])
                self.env.pop()
        else:
            #throw error as value is not a boolean
            super().error(ErrorType.TYPE_ERROR, f"Invalid IF condition")

    def __for_statement(self, statement):
        self.__assign(statement.dict["init"])
        condition = self.__eval_expr(statement.dict["condition"]) #removed .value() from end of this, might cause issue left here for reminder
        if(condition.type() != InterpreterBase.BOOL_NODE):
            super().error(ErrorType.TYPE_ERROR, f"Invalid For loop condition")
        while(condition.value()):
            self.env.append((EnvironmentManager(),True)) #new environment everytime
            current_return_val = self.env[-2][0].get("return")
            self.env[-1][0].create("return", Value(current_return_val.type(),current_return_val.value()))  
            self.__run_statements(statement.dict["statements"])
            self.env.pop()
            self.__assign(statement.dict["update"])
            condition = self.__eval_expr(statement.dict["condition"])


        

    def __call_func(self, call_node):
        func_name = call_node.get("name")
        if func_name == "print":
            return self.__call_print(call_node)
        if func_name == "inputi":
            return self.__call_input(call_node)
        if func_name == "inputs":
            return self.__call_input(call_node)

        # add code here later to call other functions
        arguments = call_node.dict["args"]
        func_name = func_name + "+" + str(len(arguments)) #using our naming scheme for custom function
        if func_name in self.func_name_to_ast:
            function_args = self.func_name_to_ast[func_name].dict["args"]
            function_scope = EnvironmentManager()
            #self.env.append((EnvironmentManager(),False)) #cannot go out of scope with the function
            #define the passed in arguments for our scope
            for i in range(len(function_args)):
                #define newly created argument
                var_name = function_args[i].dict["name"]
                function_scope.create(var_name, Value(Type.INT, 0)) #create our argument
                value_obj = self.__eval_expr(arguments[i])
                function_scope.set(var_name,value_obj) #set our argument
            #set our default return value to be nil
            self.env.append((function_scope,False))
            self.env[-1][0].create("return", Value(InterpreterBase.NIL_DEF, InterpreterBase.NIL_DEF))
            self.__run_statements(self.func_name_to_ast[func_name].dict["statements"])
            returnValue = self.env[-1][0].get("return")
            self.env.pop()
        else:
            super().error(ErrorType.NAME_ERROR, f"Function not found")
        return returnValue

    def __call_print(self, call_ast):
        output = ""
        for arg in call_ast.get("args"):
            result = self.__eval_expr(arg)  # result is a Value object
            addPrint = get_printable(result)
            if(type(addPrint) == bool):
                addPrint = str(addPrint).lower()
            else:
                addPrint = str(addPrint)
            output = output + addPrint
        super().output(output)
        return Value(InterpreterBase.NIL_NODE,InterpreterBase.NIL_DEF)


    def __call_input(self, call_ast):
        args = call_ast.get("args")
        if args is not None and len(args) == 1:
            result = self.__eval_expr(args[0])
            super().output(get_printable(result))
        elif args is not None and len(args) > 1:
            super().error(
                ErrorType.NAME_ERROR, "No inputi() function that takes > 1 parameter"
            )
        inp = super().get_input()
        if call_ast.get("name") == "inputi":
            return Value(Type.INT, int(inp))
        # we can support inputs here later
        if call_ast.get("name") == "inputs":
            return Value(Type.STRING,str(inp))

    def __assign(self, assign_ast):
        var_name = assign_ast.get("name")
        value_obj = self.__eval_expr(assign_ast.get("expression"))
        currentScope = self.env[-1]
        currentIndex = len(self.env) - 1
        while(currentScope[1] == True and currentScope[0].get(var_name) is None and currentIndex > 0):
            currentIndex -= 1
            currentScope = self.env[currentIndex]
        if not currentScope[0].set(var_name, value_obj):
            super().error(
                ErrorType.NAME_ERROR, f"Undefined variable {var_name} in assignment"
            )

    def __var_def(self, var_ast):
        var_name = var_ast.get("name")
        if not self.env[len(self.env)-1][0].create(var_name, Value(Type.INT, 0)):
            super().error(
                ErrorType.NAME_ERROR, f"Duplicate definition for variable {var_name}"
            )

    def __eval_expr(self, expr_ast):
        if expr_ast.elem_type == InterpreterBase.NIL_NODE:
            return Value(InterpreterBase.NIL_NODE, InterpreterBase.NIL_DEF)
        if expr_ast.elem_type == InterpreterBase.INT_NODE:
            return Value(Type.INT, expr_ast.get("val"))
        if expr_ast.elem_type == InterpreterBase.STRING_NODE:
            return Value(Type.STRING, expr_ast.get("val"))
        if expr_ast.elem_type == InterpreterBase.VAR_NODE:
            var_name = expr_ast.get("name")
            val = None
            for i in range(len(self.env)-1,-1,-1):
                currentScope = self.env[i]
                val = currentScope[0].get(var_name)
                if(currentScope[1] == False or not (val is None)):
                    break
            if val is None:
                super().error(ErrorType.NAME_ERROR, f"Variable {var_name} not found")
            return val
        #For booleans
        if expr_ast.elem_type == InterpreterBase.BOOL_NODE:
            return Value(Type.BOOL,expr_ast.get("val"))
        if expr_ast.elem_type == Interpreter.NEG_NODE:
            operandValue = self.__eval_expr(expr_ast.dict["op1"])
            if(operandValue.type() == InterpreterBase.INT_NODE):
                return Value(Type.INT,-1 * operandValue.value())
            else:
                super().error(ErrorType.TYPE_ERROR, f"Invalid Type with operation")
        if expr_ast.elem_type == Interpreter.NOT_NODE:
            operandValue = self.__eval_expr(expr_ast.dict["op1"])
            if(operandValue.type() != InterpreterBase.BOOL_NODE):
                super().error(ErrorType.TYPE_ERROR, f"Invalid Type with operation")
            return Value(Type.BOOL,not operandValue.value())
        #Function Call
        if expr_ast.elem_type == InterpreterBase.FCALL_NODE:
            return self.__call_func(expr_ast)
        #Binary Operations
        if expr_ast.elem_type in Interpreter.BIN_OPS:
            return self.__eval_op(expr_ast)


    def __eval_op(self, arith_ast):
        left_value_obj = self.__eval_expr(arith_ast.get("op1"))
        right_value_obj = self.__eval_expr(arith_ast.get("op2"))
        if left_value_obj.type() != right_value_obj.type():

            if(arith_ast.elem_type == "=="):
                return Value(InterpreterBase.BOOL_NODE,False)
            elif(arith_ast.elem_type == "!="):
                return Value(InterpreterBase.BOOL_NODE, True)
            super().error(
                ErrorType.TYPE_ERROR,
                f"Incompatible types for {arith_ast.elem_type} operation",
            )
        if arith_ast.elem_type not in self.op_to_lambda[left_value_obj.type()]:
            super().error(
                ErrorType.TYPE_ERROR,
                f"Incompatible operator {arith_ast.elem_type} for type {left_value_obj.type()}",
            )
        f = self.op_to_lambda[left_value_obj.type()][arith_ast.elem_type]
        return f(left_value_obj, right_value_obj)

    def __setup_ops(self):
        self.op_to_lambda = {}
        # set up operations on integers
        self.op_to_lambda[Type.INT] = {}
        self.op_to_lambda[Type.INT]["+"] = lambda x, y: Value(
            x.type(), x.value() + y.value()
        )
        self.op_to_lambda[Type.INT]["-"] = lambda x, y: Value(
            x.type(), x.value() - y.value()
        )
        self.op_to_lambda[Type.INT]["*"] = lambda x, y: Value(
            x.type(), x.value() * y.value()
        )
        self.op_to_lambda[Type.INT]["/"] = lambda x, y: Value(
            x.type(), x.value() // y.value()
        )
        self.op_to_lambda[Type.INT]["=="] = lambda x, y: Value(
            InterpreterBase.BOOL_NODE, x.value() == y.value()
        )
        self.op_to_lambda[Type.INT]["!="] = lambda x, y: Value(
            InterpreterBase.BOOL_NODE, x.value() != y.value()
        )
        self.op_to_lambda[Type.INT]["<"] = lambda x, y: Value(
            InterpreterBase.BOOL_NODE, x.value() < y.value()
        )
        self.op_to_lambda[Type.INT]["<="] = lambda x, y: Value(
            InterpreterBase.BOOL_NODE, x.value() <= y.value()
        )
        self.op_to_lambda[Type.INT][">"] = lambda x, y: Value(
            InterpreterBase.BOOL_NODE, x.value() > y.value()
        )
        self.op_to_lambda[Type.INT][">="] = lambda x, y: Value(
            InterpreterBase.BOOL_NODE, x.value() >= y.value()
        )
        # add other operators here later for int, string, bool, etc
        # String operations:
        self.op_to_lambda[Type.STRING] = {}
        self.op_to_lambda[Type.STRING]["+"] = lambda x, y: Value(
            x.type(), x.value() + y.value()
        )
        self.op_to_lambda[Type.STRING]["=="] = lambda x, y: Value(
            InterpreterBase.BOOL_NODE, x.value() == y.value()
        )
        self.op_to_lambda[Type.STRING]["!="] = lambda x, y: Value(
            InterpreterBase.BOOL_NODE, x.value() != y.value()
        )

        # Bool operations
        self.op_to_lambda[Type.BOOL] = {}
        self.op_to_lambda[Type.BOOL]["=="] = lambda x, y: Value(
            x.type(), x.value() == y.value()
        )
        self.op_to_lambda[Type.BOOL]["!="] = lambda x, y: Value(
            x.type(), x.value() != y.value()
        )
        self.op_to_lambda[Type.BOOL]["||"] = lambda x, y: Value(
            x.type(), x.value() | y.value()
        )
        self.op_to_lambda[Type.BOOL]["&&"] = lambda x, y: Value(
            x.type(), x.value() & y.value()
        )

        #Nil Operations
        self.op_to_lambda[InterpreterBase.NIL_NODE] = {}
        self.op_to_lambda[InterpreterBase.NIL_NODE]["=="] = lambda x, y: Value(
            Type.BOOL, x.type() == y.type()
        )
        self.op_to_lambda[InterpreterBase.NIL_NODE]["!="] = lambda x, y: Value(
            Type.BOOL, x.type() != y.type()
        )



