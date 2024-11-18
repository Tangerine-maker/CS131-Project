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
    ALONE = 3


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
        self.__set_up_struct_table(ast)
        self.__set_up_function_table(ast)
        self.env = EnvironmentManager()
        self.__call_func_aux("main", [])

    def __set_up_struct_table(self,ast):
        self.struct_table = {} # Will basically be a dictionary of dictionaries with each struct name corresponding to a dictionary with their field names
        for struct in ast.get("structs"):
            if(struct.get("name") in self.struct_table): # Barista doesn't allow duplicte definition of struct
                super().error(
                    ErrorType.TYPE_ERROR, "Duplicate Definition of Struct"
                )
                
            self.struct_table[struct.get("name")] = {}
            current_struct = self.struct_table[struct.get("name")]
            for field in struct.get("fields"):
                if(field.get("var_type") not in self.struct_table 
                    and field.get("var_type") not in [InterpreterBase.INT_NODE,InterpreterBase.STRING_NODE, InterpreterBase.BOOL_NODE]):
                        super().error(
                            ErrorType.TYPE_ERROR, "Field Does Not Exist"
                        )
                        pass # throw type error as field name does not exist
                current_struct[field.get("name")] = field.get("var_type")
            # Set up == and != for specific struct
            self.op_to_lambda[struct.get("name")] = {
                "==": lambda x, y: Value(
            Type.BOOL, (x.type() == y.type() and x.value() is y.value()) or (y.type() == InterpreterBase.NIL_NODE and x.value() == y.value())
        ),
                "!=": lambda x, y: Value(
            Type.BOOL, not ((x.type() == y.type() and x.value() is y.value()) or (y.type() == InterpreterBase.NIL_NODE and x.value() == y.value()))
        )
            }


    def __set_up_function_table(self, ast):
        self.func_name_to_ast = {}
        for func_def in ast.get("functions"):
            func_name = func_def.get("name")
            num_params = len(func_def.get("args"))
            if func_name not in self.func_name_to_ast:
                self.func_name_to_ast[func_name] = {}
            self.func_name_to_ast[func_name][num_params] = func_def

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
            if status == ExecStatus.RETURN or status == ExecStatus.ALONE:
                self.env.pop_block()
                return (status, return_val)

        self.env.pop_block()
        return (ExecStatus.CONTINUE, Interpreter.NIL_VALUE)

    def __run_statement(self, statement):
        status = ExecStatus.CONTINUE
        return_val = None
        if statement.elem_type == InterpreterBase.FCALL_NODE:
            self.__call_func(statement)
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
        return (status, return_val)
    
    def __call_func(self, call_node):
        func_name = call_node.get("name")
        actual_args = call_node.get("args")
        return self.__call_func_aux(func_name, actual_args)

    def __call_func_aux(self, func_name, actual_args):
        if func_name == "print":
            return self.__call_print(actual_args)
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
            result = self.__eval_expr(actual_ast)
            if(result.type() in [InterpreterBase.BOOL_NODE,InterpreterBase.INT_NODE, InterpreterBase.STRING_NODE]):
                result = copy.copy(self.__eval_expr(actual_ast)) # Pass by value
            if(formal_ast.get("var_type") == InterpreterBase.BOOL_NODE and result.type() == InterpreterBase.INT_NODE):
                result = self.__coerce(result)
            if(formal_ast.get("var_type") in self.struct_table and result.type() == InterpreterBase.NIL_NODE):
                result = Value(formal_ast.get("var_type"),InterpreterBase.NIL_NODE)
            if(formal_ast.get("var_type") != result.type()):
                super().error(
                    ErrorType.TYPE_ERROR, "Argument Type Mismatch"
                )
                pass # Throw error type mismatch for parameters
            
            arg_name = formal_ast.get("name")
            args[arg_name] = result

        # then create the new activation record 
        self.env.push_func()
        # and add the formal arguments to the activation record
        for arg_name, value in args.items():
          self.env.create(arg_name, value,value.type())
        return_status, return_val = self.__run_statements(func_ast.get("statements"))
        if(func_ast.get("return_type") is None): # Main function only, do nothing
            pass
        elif(func_ast.get("return_type") == InterpreterBase.VOID_DEF):
            if(return_status == ExecStatus.RETURN):
                super().error(
                    ErrorType.TYPE_ERROR, "Invalid return for void function"
                )
            if(return_status == ExecStatus.ALONE):
                return_val = None
                pass
        elif(return_status == ExecStatus.CONTINUE or return_status == ExecStatus.ALONE):
            # Return default values
            return_val = self.__get_default(func_ast.get("return_type"))
        else: # Means it returned something
            if(return_val.type() == InterpreterBase.INT_NODE and func_ast.get("return_type") == InterpreterBase.BOOL_NODE):
                return_val = self.__coerce(copy.copy(return_val))
            elif(return_val.type() == InterpreterBase.NIL_NODE and func_ast.get("return_type") in self.struct_table):
                return_val = Value(func_ast.get("return_type"),InterpreterBase.NIL_DEF)
            elif(func_ast.get("return_type") in self.struct_table):
                pass # If returning a struct, return the object reference so we do nothing basically
            elif(return_val.type() != func_ast.get("return_type")):
                super().error(
                    ErrorType.TYPE_ERROR, "Invalid return type"
                )
                pass # Throw error
            else:
                return_val = copy.copy(return_val) # return by value
        self.env.pop_func()
        return return_val

    def __call_print(self, args):
        output = ""
        for arg in args:
            result = self.__eval_expr(arg)  # result is a Value object
            if(result is None):
                super().error(
                    ErrorType.TYPE_ERROR, "Cannot print out a void function"
                )
            if(result.type() in self.struct_table):
                if(result.value() == InterpreterBase.NIL_DEF):
                    newWord = "nil"
                else:
                    output = "None" # This happens in barista so I will follow this
                    break
            else:
                newWord = get_printable(result)
            if(newWord == None):
                super().error(
                    ErrorType.TYPE_ERROR, "Cannot print out a void function"
                )
            output = output + newWord
        super().output(output)

    def __call_input(self, name, args):
        if args is not None and len(args) == 1:
            result = self.__eval_expr(args[0])
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

    def __coerce(self, val):
        if(val.value() == 0):
            return Value(InterpreterBase.BOOL_NODE, False)
        return Value(InterpreterBase.BOOL_NODE,True)

    def __assign(self, assign_ast):
        var_name = assign_ast.get("name")
        value_obj = self.__eval_expr(assign_ast.get("expression"))
        value_type = value_obj.type()
        if("." in var_name): # If dot operator is used
            x = var_name.split('.')
            base_object = x[0]
            
            topObject = self.env.get(base_object) # We will pass this into the set 
            if(topObject is None): # Means struct is undefined
                super().error(
                    ErrorType.NAME_ERROR, f"Value was not found"
                )
            currentStruct = self.env.get(base_object)
            if(currentStruct.value() == InterpreterBase.NIL_NODE):
                super().error(
                    ErrorType.FAULT_ERROR, f"NIL REFERENCE USED"
                )
            if(currentStruct.type() not in self.struct_table):
                super().error(
                    ErrorType.TYPE_ERROR, f"USED DOT OPERATOR ON NON STRUCT OBJECT"
                )
            for i in range(1,len(x)-1):
                field_name = x[i]
                if(currentStruct.value() == InterpreterBase.NIL_NODE):
                    super().error(
                        ErrorType.FAULT_ERROR, f"NIL REFERENCE USED"
                    )   
                if(currentStruct.type() not in self.struct_table):
                    super().error(
                        ErrorType.TYPE_ERROR, f"USED DOT OPERATOR ON NON STRUCT OBJECT"
                    )
                if(field_name not in currentStruct.value()):
                    super().error(
                        ErrorType.NAME_ERROR, f"INVALID FIELD"
                    )
                currentStruct = currentStruct.value()[field_name]
            field_name = x[-1]
            struct_type = topObject.type()
            val = currentStruct.value()
            
            if(currentStruct.type() not in self.struct_table):
                super().error(
                    ErrorType.TYPE_ERROR, f"USED DOT OPERATOR ON NON STRUCT OBJECT"
                )
            if(field_name not in val):
                super().error(
                    ErrorType.NAME_ERROR, f"INVALID FIELD"
                )
            if(value_obj.type() == InterpreterBase.INT_NODE and val[field_name].type() == InterpreterBase.BOOL_NODE):
                value_obj = self.__coerce(value_obj)
            if(value_obj.type() == InterpreterBase.NIL_NODE):
                value_obj = Value(val[field_name].type(),InterpreterBase.NIL_DEF)
            if(value_obj.type() != val[field_name].type()):
                super().error(
                    ErrorType.TYPE_ERROR, f"NON MATCHING TYPES"
                )
            val[field_name] = value_obj
            value_obj = topObject
            value_type = topObject.type()
            var_name = base_object
        current_val = self.env.get(var_name)
        if(current_val.type() == InterpreterBase.BOOL_NODE and value_type == InterpreterBase.INT_NODE):
            value_obj = self.__coerce(value_obj)
            value_type = InterpreterBase.BOOL_NODE
        if(current_val.type() in self.struct_table and value_type == InterpreterBase.NIL_NODE): # We are allowed to set a struct to nil
            value_obj = Value(current_val.type(), InterpreterBase.NIL_DEF)
            value_type = current_val.type()
            
        set_status = self.env.set(var_name, value_obj,value_type)
        if(set_status == "FAIL"):
            super().error(
                ErrorType.NAME_ERROR, f"Undefined variable {var_name} in assignment"
            )
        elif(set_status == "INV"):
            super().error(
                ErrorType.TYPE_ERROR, f"Incompatible type assignment"
            )
    
    def __get_default(self,var_type):
        match var_type:
            case InterpreterBase.INT_NODE:
                return Value(InterpreterBase.INT_NODE,0)
            case InterpreterBase.STRING_NODE:
                return Value(InterpreterBase.STRING_NODE,"")
            case InterpreterBase.BOOL_NODE:
                return Value(InterpreterBase.BOOL_NODE,False)
            case other: # Will eventually be used for structs
                if(other in self.struct_table):
                    return Value(var_type,InterpreterBase.NIL_DEF)
                else:
                    super().error(
                        ErrorType.TYPE_ERROR, "Unknown type used"
                    )
                    pass # Throw error as type does not exist

    def __var_def(self, var_ast):
        var_name = var_ast.get("name")
        var_type = var_ast.get("var_type")
        default_value = self.__get_default(var_type)
        if not self.env.create(var_name, default_value,var_type):
            super().error(
                ErrorType.NAME_ERROR, f"Duplicate definition for variable {var_name}"
            )

    def __eval_expr(self, expr_ast):
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
            if("." in var_name): # If dot operator is used so structs
                splitted = var_name.split('.')
                start = splitted[0]
                val = self.env.get(start)
                for i in range(1,len(splitted)):
                    field = splitted[i]
                    if(val.value() == InterpreterBase.NIL_NODE):
                        super().error(
                            ErrorType.FAULT_ERROR, f"NIL REFERENCE USED"
                        )
                    if(val.type() not in self.struct_table):
                        super().error(
                            ErrorType.TYPE_ERROR, f"USED DOT OPERATOR ON NON STRUCT OBJECT"
                        )
                    if(field not in val.value()):
                        super().error(
                            ErrorType.NAME_ERROR, f"INVALID FIELD"
                        )
                    val = val.value()[field]

            else:
                val = self.env.get(var_name)
                if val is None:
                    super().error(ErrorType.NAME_ERROR, f"Variable {var_name} not found")
            return val
        if expr_ast.elem_type == InterpreterBase.NEW_NODE:
            found_struct = self.struct_table[expr_ast.get("var_type")]
            default_vals = {}
            for field in found_struct:
                default_vals[field] = self.__get_default(found_struct[field]) # Get default value for each field of the struct
            return Value(expr_ast.get("var_type"),default_vals)
        if expr_ast.elem_type == InterpreterBase.FCALL_NODE:
            return self.__call_func(expr_ast)
        if expr_ast.elem_type in Interpreter.BIN_OPS:
            return self.__eval_op(expr_ast)
        if expr_ast.elem_type == Interpreter.NEG_NODE:
            return self.__eval_unary(expr_ast, Type.INT, lambda x: -1 * x)
        if expr_ast.elem_type == Interpreter.NOT_NODE:
            return self.__eval_unary(expr_ast, Type.BOOL, lambda x: not x)

    def __eval_op(self, arith_ast):
        left_value_obj = self.__eval_expr(arith_ast.get("op1"))
        right_value_obj = self.__eval_expr(arith_ast.get("op2"))
        if(left_value_obj is None or right_value_obj is None):
            super().error(
                    ErrorType.TYPE_ERROR,
                    "Incompatible type for for condition",
                )
        if(arith_ast.elem_type in ["||", "&&"]):
            if(left_value_obj.type() == InterpreterBase.INT_NODE):
                left_value_obj = self.__coerce(left_value_obj)
            if(right_value_obj.type() == InterpreterBase.INT_NODE):
                right_value_obj = self.__coerce(right_value_obj)
        if(left_value_obj.type() == InterpreterBase.NIL_DEF): # I do not know why eval_expr for Nil returns just "Nil" and not a value. but I will keep it that way since I will not question Carey
            left_value_obj = Value(InterpreterBase.NIL_NODE,InterpreterBase.NIL_DEF)
        if(right_value_obj.type() == InterpreterBase.NIL_DEF):
            right_value_obj = Value(InterpreterBase.NIL_DEF,InterpreterBase.NIL_DEF)
        if(arith_ast.elem_type in ["&&","||","==","!="]):
            if((left_value_obj.type() == Type.INT and right_value_obj.type() == Type.BOOL) or
            (left_value_obj.type() == Type.BOOL and right_value_obj.type() == Type.INT)): # Coercian
                if(left_value_obj.type() == Type.INT):
                    left_value_obj = self.__coerce(left_value_obj)
                else:
                    right_value_obj = self.__coerce(right_value_obj)

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
        f = self.op_to_lambda[left_value_obj.type()][arith_ast.elem_type]
        return f(left_value_obj, right_value_obj)
    def _dot_operator(self, statement):
        var_name = statement.get("name")
        object_name, field_name = var_name.split('.')
        x = var_name.split('.')
        struct_type = self.env.get(object_name).type()
        currentStruct = self.env.get(object_name)
        val = currentStruct.value()
        if(currentStruct.value() == InterpreterBase.NIL_NODE):
            super().error(
                ErrorType.TYPE_ERROR,
                "Incompatible type for if condition",
            )
        if(currentStruct.type() not in self.struct_table):
            super().error(
                ErrorType.TYPE_ERROR, f"USED DOT OPERATOR ON NON STRUCT OBJECT"
            )
        if(field_name not in val):
            super().error(
                ErrorType.NAME_ERROR, f"INVALID FIELD"
            )
        val = val[field_name]
        return val
    def __compatible_types(self, oper, obj1, obj2):
        if((obj1.type() == InterpreterBase.NIL_NODE and obj2.type() in self.struct_table) or
           (obj1.type() in self.struct_table and obj2.type() == InterpreterBase.NIL_NODE)):
            return True
        return obj1.type() == obj2.type()

    def __eval_unary(self, arith_ast, t, f):
        value_obj = self.__eval_expr(arith_ast.get("op1"))
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
            Type.BOOL, (x.type() == y.type() or y.type() in self.struct_table) and x.value() == y.value()
        )
        self.op_to_lambda[Type.NIL]["!="] = lambda x, y: Value(
            Type.BOOL, (x.type() != y.type() and y.type() not in self.struct_table) or x.value() != y.value()
        )

    def __do_if(self, if_ast):
        cond_ast = if_ast.get("condition")
        result = self.__eval_expr(cond_ast)

        if(result.type() == Type.INT):
            result = self.__coerce(result)
        elif result.type() != Type.BOOL:
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

    def __do_for(self, for_ast):
        init_ast = for_ast.get("init") 
        cond_ast = for_ast.get("condition")
        update_ast = for_ast.get("update") 

        self.__run_statement(init_ast)  # initialize counter variable
        run_for = Interpreter.TRUE_VALUE
        while run_for.value():
            run_for = self.__eval_expr(cond_ast)  # check for-loop condition
            if(run_for.type() == Type.INT):
                run_for = self.__coerce(run_for)
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
        if expr_ast is None: # Means they called return by itself (return;)
            return (ExecStatus.ALONE, Interpreter.NIL_VALUE)
        value_obj = self.__eval_expr(expr_ast)
        return (ExecStatus.RETURN, value_obj)


