a = [1, 2, 3]
b = a
print(id(a), id(b))
import copy
c = copy.deepcopy(b)
print(id(b), id(c))
b[2] = 4
print(a)