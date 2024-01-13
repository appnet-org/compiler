local socket = require("socket")
math.randomseed(socket.gettime()*1000)
math.random();

local function randomString(length)
    local str = ""
    for i = 1, length do
        str = str .. string.char(math.random(97, 122)) -- Generates a random lowercase letter
    end
    return str
end

local function req1()
    local method = "GET"
    local str = randomString(100)
    local path = "http://10.96.88.88:8080/ping-echo?body=" .. str
    local headers = {}
    return wrk.format(method, path, headers, str)
end

local function req2()
    local method = "GET"
    local path = "http://10.96.88.88:8080/ping-echo?body=test"
    local headers = {}
    return wrk.format(method, path, headers, str)
end

request = function()

    local req1_ratio  = 0.95
    local req2_ratio   = 1 - req1_ratio

    local coin = math.random()
    if coin < req1_ratio then
        return req1()
    else
        return req2()
    end
end
