# document that we won't have a return inside the init/update of a for loop

import copy
from enum import Enum

from brewparse import parse_program
from env_v2 import EnvironmentManager
from intbase import InterpreterBase, ErrorType
from type_valuev2 import Type, Value, create_value, get_printable


class ExecStatus(Enum):
    CONTINUE = 1
    RETURN = 2
    EXCEPTION = 3


class Expression: # Needed for lazy evaluation
    def __init__(self,expression):
        self.cached = False
        self.value = expression
    def set_value(self,value):
        self.value = value
        self.cached = True
    def __str__(self):
        return f"Is Cached: {self.cached} Value: {self.value}"
# Main interpreter class
class Interpreter(InterpreterBase):
    # constants
    NIL_VALUE = create_value(InterpreterBase.NIL_DEF)
    TRUE_VALUE = create_value(InterpreterBase.TRUE_DEF)
    BIN_OPS = {"+", "-", "*", "/", "==", "!=", ">", ">=", "<", "<=", "||", "&&"}

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
        self.env = EnvironmentManager()
        self.__call_func_aux("main", [])

    def __set_up_function_table(self, ast):
        self.func_name_to_ast = {}
        for func_def in ast.get("functions"):
            func_name = func_def.get("name")
            num_params = len(func_def.get("args"))
            if func_name not in self.func_name_to_ast:
                self.func_name_to_ast[func_name] = {}
            self.func_name_to_ast[func_name][num_params] = func_def
        print(self.func_name_to_ast)

    def __get_func_by_name(self, name, num_params):
        if name not in self.func_name_to_ast:
            super().error(ErrorType.NAME_ERROR, f"Function {name} not found")
        candidate_funcs = self.func_name_to_ast[name]
        if num_params not in candidate_funcs:
            super().error(
                ErrorType.NAME_ERROR,
                f"Function {name} taking {num_params} params not found",
            )
        return candidate_funcs[num_params]

    def __run_statements(self, statements):
        self.env.push_block()
        for statement in statements:
            if self.trace_output:
                print(statement)
            status, return_val = self.__run_statement(statement)
            if status == ExecStatus.RETURN or status == ExecStatus.EXCEPTION:
                self.env.pop_block()
                return (status, return_val)

        self.env.pop_block()
        return (ExecStatus.CONTINUE, Interpreter.NIL_VALUE)

    def __run_statement(self, statement):
        status = ExecStatus.CONTINUE
        return_val = None
        if statement.elem_type == InterpreterBase.FCALL_NODE:
            return_val = self.__call_func(statement)
            if(return_val.type() == "EXCEPTION"):
                status = ExecStatus.EXCEPTION
                return_val = Value(InterpreterBase.STRING_NODE,return_val.value())
            else:
                return_val = None # Basically just check whether or not a standalone function call resulted in an exception, if not just reset things to normal
        elif statement.elem_type == "=":
            self.__assign(statement)
        elif statement.elem_type == InterpreterBase.VAR_DEF_NODE:
            self.__var_def(statement)
        elif statement.elem_type == InterpreterBase.RETURN_NODE:
            status, return_val = self.__do_return(statement)
        elif statement.elem_type == Interpreter.IF_NODE:
            status, return_val = self.__do_if(statement)
        elif statement.elem_type == Interpreter.FOR_NODE:
            status, return_val = self.__do_for(statement)
        elif statement.elem_type == InterpreterBase.TRY_NODE:
            status, return_val = self.__do_try(statement)
        elif statement.elem_type == InterpreterBase.RAISE_NODE:
            status, return_val = self.__do_raise(statement)

        return (status, return_val)

    def __call_func(self, call_node):
        func_name = call_node.get("name")
        actual_args = call_node.get("args")
        return self.__call_func_aux(func_name, actual_args)

    def __call_func_aux(self, func_name, actual_args):
        if func_name == "print":
            return_value =  self.__call_print(actual_args)
            return return_value
        if func_name == "inputi" or func_name == "inputs":
            return self.__call_input(func_name, actual_args)

        func_ast = self.__get_func_by_name(func_name, len(actual_args))
        formal_args = func_ast.get("args")
        if len(actual_args) != len(formal_args):
            super().error(
                ErrorType.NAME_ERROR,
                f"Function {func_ast.get('name')} with {len(actual_args)} args not found",
            )

        # first evaluate all of the actual parameters and associate them with the formal parameter names
        args = {}
        for formal_ast, actual_ast in zip(formal_args, actual_args):
            result = self.__lazy_setup(actual_ast) # Must be done lazily
            result = Expression(result)
            arg_name = formal_ast.get("name")
            args[arg_name] = result

        # then create the new activation record 
        self.env.push_func()
        # and add the formal arguments to the activation record
        for arg_name, value in args.items():
          self.env.create(arg_name, value)
        status, return_val = self.__run_statements(func_ast.get("statements"))
        if(status == ExecStatus.EXCEPTION and func_name == "main"):
            # Means we have an uncaught exception
            super().error(
                ErrorType.FAULT_ERROR,
                f"Uncaught exception",
            )
        elif(status == ExecStatus.EXCEPTION):
            # Return a special value indicating the exception we have
            return_val = Value("EXCEPTION",return_val.value())
        self.env.pop_func()
        return return_val

    def __call_print(self, args):
        output = ""
        for arg in args:
            result = self.__eval_expr(arg)  # result is a Value object and eagerly evaluated
            while(type(result) == Expression): # If we hit a return value in our arguments
                result = self.__eval_expr(result)
            if(result.type() == "EXCEPTION"):
                return result
            output = output + get_printable(result)
        super().output(output)
        return Interpreter.NIL_VALUE

    def __call_input(self, name, args):
        if args is not None and len(args) == 1:
            result = self.__eval_expr(args[0])
            while(type(result) == Expression):
                result = self.__eval_expr(result)
            super().output(get_printable(result))
        elif args is not None and len(args) > 1:
            super().error(
                ErrorType.NAME_ERROR, "No inputi() function that takes > 1 parameter"
            )
        inp = super().get_input()
        if name == "inputi":
            return Value(Type.INT, int(inp))
        if name == "inputs":
            return Value(Type.STRING, inp)

    def __assign(self, assign_ast):
        var_name = assign_ast.get("name")
        #value_obj = self.__eval_expr(assign_ast.get("expression"))
        value_obj = assign_ast.get("expression")
        value_obj = self.__lazy_setup(value_obj)
        value_obj = Expression(value_obj)
        # Recursively replace each variable with its corresponding expression (lazy eval as we are just replacing the variable name with the expression its pointing to)
        if not self.env.set(var_name, value_obj):
            super().error(
                ErrorType.NAME_ERROR, f"Undefined variable {var_name} in assignment"
            )
    
    def __get_equivalent(self,expression):
        if(expression.elem_type in Interpreter.BIN_OPS):
            for i in expression.dict:
                expression.dict[i] = self.__get_equivalent(expression.get(i))
        elif(expression.elem_type == "var"):
            value = self.env.get(expression.get("name"))
            if(value is None): # Means that the variable is pointing at nothing (Either undefined or not initialized)
                expression.elem_type = "none"
                expression.dict["val"] = None
            elif(type(value) == Value): # This means we already have a cached value for our function
                #TODO LAZY EVAL FOR FUNCTIONS MEANING THAT IT SHOULD SAVE THE ELEMENT NOT THE VALUE WHEN IT IS PASSED IN
                expression.elem_type = value.type()
                expression.dict = {"val":value.value()}
            else:
                value = self.__get_equivalent(value)
                expression = value
        elif(expression.elem_type == "fcall"):
            arguments = expression.get("args")
            for i in range(len(arguments)):
                arguments[i] = self.__get_equivalent(arguments[i])
            expression.dict["args"] = arguments
        return expression

    def __lazy_setup(self,expression):
        if(type(expression) == Expression):
            return expression
        if(expression.elem_type in Interpreter.BIN_OPS):
            for i in expression.dict:
                expression.dict[i] = self.__lazy_setup(expression.get(i))
        elif(expression.elem_type == "var"): # If its a variable, it already has a corresponding expression object
            var_name = expression.get("name")
            value = self.env.get(var_name)
            # Implement error checking here if var_name doesn't exist remember its lazy so error only happens when it actuall gets run, idea make error expression obj
            expression = value
            return expression
        elif(expression.elem_type == "fcall"): # Worry about this later
            arguments = expression.get("args")
            for i in range(len(arguments)):
                lazy_result = self.__lazy_setup(arguments[i])
                arguments[i] = self.__lazy_setup(arguments[i])
            expression.dict["args"] = arguments
        
        return expression


    def __var_def(self, var_ast):
        var_name = var_ast.get("name")
        if not self.env.create(var_name, Interpreter.NIL_VALUE):
            super().error(
                ErrorType.NAME_ERROR, f"Duplicate definition for variable {var_name}"
            )

    def __eval_expr(self, expr_ast):
        if(type(expr_ast) == Expression):
            if(expr_ast.cached):
                return expr_ast.value
            elif(not expr_ast.cached):
                evaluation = self.__eval_expr(expr_ast.value)
                while(type(evaluation) == Expression):
                    evaluation = self.__eval_expr(evaluation)
                expr_ast.set_value(evaluation) # Add checking for error expression
                return expr_ast.value
        if expr_ast.elem_type == InterpreterBase.NIL_NODE:
            return Interpreter.NIL_VALUE
        if expr_ast.elem_type == InterpreterBase.INT_NODE:
            return Value(Type.INT, expr_ast.get("val"))
        if expr_ast.elem_type == InterpreterBase.STRING_NODE:
            return Value(Type.STRING, expr_ast.get("val"))
        if expr_ast.elem_type == InterpreterBase.BOOL_NODE:
            return Value(Type.BOOL, expr_ast.get("val"))
        if expr_ast.elem_type == InterpreterBase.VAR_NODE:
            var_name = expr_ast.get("name")
            val = self.env.get(var_name) # This will not get an expression object or None
            if val is None:
                super().error(ErrorType.NAME_ERROR, f"Variable {var_name} not found")
            if(val.cached): # If value is cached already that means val.value is already a Value object
                val = val.value
            elif(not val.cached):
                evaluation = self.__eval_expr(val.value)
                while(type(evaluation) == Expression):
                    evaluation = self.__eval_expr(evaluation)
                val.set_value(evaluation)
                val = val.value
            else: # Strictly for internal interpreter error checking only
                exit(20)
            return val
        if expr_ast.elem_type == InterpreterBase.FCALL_NODE:
            return self.__call_func(expr_ast)
        if expr_ast.elem_type in Interpreter.BIN_OPS:
            return self.__eval_op(expr_ast)
        if expr_ast.elem_type == Interpreter.NEG_NODE:
            return self.__eval_unary(expr_ast, Type.INT, lambda x: -1 * x)
        if expr_ast.elem_type == Interpreter.NOT_NODE:
            return self.__eval_unary(expr_ast, Type.BOOL, lambda x: not x)
        if expr_ast.elem_type == "none":
            # This means in lazy evaluation, we tried to use a variable that was pointing to none
            return Value("None",None)

    def __eval_op(self, arith_ast):
        left_value_obj = self.__eval_expr(arith_ast.get("op1"))
        if(type(left_value_obj) == Expression):
            left_value_obj = self.__eval_expr(left_value_obj)
        if(left_value_obj.type() == InterpreterBase.BOOL_NODE and left_value_obj.value() == False):
            if(arith_ast.elem_type == "&&"):
                return Value(InterpreterBase.BOOL_NODE,False)
        if(left_value_obj.type() == InterpreterBase.BOOL_NODE and left_value_obj.value() == True):
            if(arith_ast.elem_type == "||"):
                return Value(InterpreterBase.BOOL_NODE,True)
        right_value_obj = self.__eval_expr(arith_ast.get("op2"))
        if(type(right_value_obj) == Expression):
            right_value_obj = self.__eval_expr(right_value_obj)
        if not self.__compatible_types(
            arith_ast.elem_type, left_value_obj, right_value_obj
        ):
            super().error(
                ErrorType.TYPE_ERROR,
                f"Incompatible types for {arith_ast.elem_type} operation",
            )
        if arith_ast.elem_type not in self.op_to_lambda[left_value_obj.type()]:
            super().error(
                ErrorType.TYPE_ERROR,
                f"Incompatible operator {arith_ast.elem_type} for type {left_value_obj.type()}",
            )
        if(arith_ast.elem_type == "/" and right_value_obj.value() == 0):
            return Value("EXCEPTION","div0") # Generate division by zero exception
        f = self.op_to_lambda[left_value_obj.type()][arith_ast.elem_type]
        return f(left_value_obj, right_value_obj)

    def __compatible_types(self, oper, obj1, obj2):
        # DOCUMENT: allow comparisons ==/!= of anything against anything
        if oper in ["==", "!="]:
            return True
        return obj1.type() == obj2.type()

    def __eval_unary(self, arith_ast, t, f):
        value_obj = self.__eval_expr(arith_ast.get("op1"))
        if(type(value_obj) == Expression):
            value_obj = self.__eval_expr(value_obj)
        if value_obj.type() != t:
            super().error(
                ErrorType.TYPE_ERROR,
                f"Incompatible type for {arith_ast.elem_type} operation",
            )
        return Value(t, f(value_obj.value()))

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
            Type.BOOL, x.type() == y.type() and x.value() == y.value()
        )
        self.op_to_lambda[Type.INT]["!="] = lambda x, y: Value(
            Type.BOOL, x.type() != y.type() or x.value() != y.value()
        )
        self.op_to_lambda[Type.INT]["<"] = lambda x, y: Value(
            Type.BOOL, x.value() < y.value()
        )
        self.op_to_lambda[Type.INT]["<="] = lambda x, y: Value(
            Type.BOOL, x.value() <= y.value()
        )
        self.op_to_lambda[Type.INT][">"] = lambda x, y: Value(
            Type.BOOL, x.value() > y.value()
        )
        self.op_to_lambda[Type.INT][">="] = lambda x, y: Value(
            Type.BOOL, x.value() >= y.value()
        )
        #  set up operations on strings
        self.op_to_lambda[Type.STRING] = {}
        self.op_to_lambda[Type.STRING]["+"] = lambda x, y: Value(
            x.type(), x.value() + y.value()
        )
        self.op_to_lambda[Type.STRING]["=="] = lambda x, y: Value(
            Type.BOOL, x.value() == y.value()
        )
        self.op_to_lambda[Type.STRING]["!="] = lambda x, y: Value(
            Type.BOOL, x.value() != y.value()
        )
        #  set up operations on bools
        self.op_to_lambda[Type.BOOL] = {}
        self.op_to_lambda[Type.BOOL]["&&"] = lambda x, y: Value(
            x.type(), x.value() and y.value()
        )
        self.op_to_lambda[Type.BOOL]["||"] = lambda x, y: Value(
            x.type(), x.value() or y.value()
        )
        self.op_to_lambda[Type.BOOL]["=="] = lambda x, y: Value(
            Type.BOOL, x.type() == y.type() and x.value() == y.value()
        )
        self.op_to_lambda[Type.BOOL]["!="] = lambda x, y: Value(
            Type.BOOL, x.type() != y.type() or x.value() != y.value()
        )

        #  set up operations on nil
        self.op_to_lambda[Type.NIL] = {}
        self.op_to_lambda[Type.NIL]["=="] = lambda x, y: Value(
            Type.BOOL, x.type() == y.type() and x.value() == y.value()
        )
        self.op_to_lambda[Type.NIL]["!="] = lambda x, y: Value(
            Type.BOOL, x.type() != y.type() or x.value() != y.value()
        )

    def __do_if(self, if_ast):
        cond_ast = if_ast.get("condition")
        result = self.__eval_expr(cond_ast) # Eager evaluation
        while(type(result) == Expression):
            result = self.__eval_expr(result)
        if(result.type() == "EXCEPTION"):
            return (ExecStatus.EXCEPTION,Value(InterpreterBase.STRING_NODE,result.value()))
        if result.type() != Type.BOOL:
            super().error(
                ErrorType.TYPE_ERROR,
                "Incompatible type for if condition",
            )
        if result.value():
            statements = if_ast.get("statements")
            status, return_val = self.__run_statements(statements)
            return (status, return_val)
        else:
            else_statements = if_ast.get("else_statements")
            if else_statements is not None:
                status, return_val = self.__run_statements(else_statements)
                return (status, return_val)

        return (ExecStatus.CONTINUE, Interpreter.NIL_VALUE)
    
    def __do_try(self, try_ast):
        statements = try_ast.get("statements")
        status, return_val = self.__run_statements(statements)
        if(status == ExecStatus.EXCEPTION): # Exception was raised
            exception = return_val.value()
            catchers = try_ast.get("catchers")
            for catcher in catchers:
                catch_exception = catcher.get("exception_type")
                if(catch_exception == exception):
                    catch_expressions = catcher.get("statements")
                    status, return_val = self.__run_statements(catch_expressions)
                    return (status, return_val)
        return (status, return_val)

    def __do_raise(self,raise_ast):
        statement = raise_ast.get("exception_type")
        statement = Expression(self.__lazy_setup(statement))
        exception_value = self.__eval_expr(statement)
        if(exception_value.type() != InterpreterBase.STRING_NODE): # Exception generated must be a string
            super().error(
                ErrorType.TYPE_ERROR,
                "Exception is not a string",
            )

        return (ExecStatus.EXCEPTION, exception_value)
    def __do_for(self, for_ast):
        init_ast = for_ast.get("init") 
        cond_ast = for_ast.get("condition")
        update_ast = for_ast.get("update") 

        self.__run_statement(init_ast)  # initialize counter variable
        run_for = Interpreter.TRUE_VALUE
        while run_for.value():
            run_for = self.__eval_expr(cond_ast)  # check for-loop condition
            if run_for.type() != Type.BOOL:
                super().error(
                    ErrorType.TYPE_ERROR,
                    "Incompatible type for for condition",
                )
            if run_for.value():
                statements = for_ast.get("statements")
                status, return_val = self.__run_statements(statements)
                if status == ExecStatus.RETURN:
                    return status, return_val
                self.__run_statement(update_ast)  # update counter variable

        return (ExecStatus.CONTINUE, Interpreter.NIL_VALUE)

    def __do_return(self, return_ast):
        expr_ast = return_ast.get("expression")
        expr_ast = self.__lazy_setup(expr_ast)
        if expr_ast is None:
            return (ExecStatus.RETURN, Interpreter.NIL_VALUE)
        value_obj = Expression(expr_ast)
        return (ExecStatus.RETURN, value_obj)
    
if (__name__ == "__main__"):
    x = '''
func increment(n) {
  print("Incrementing", n);
  return n + 1;
}

func main() {
  var x;
  var y;
  x = increment(5);
  y = increment(x);

  print("Before evaluating y");
  print("Value of y:", y);   
}'''
gc = Interpreter()
gc.run(x)