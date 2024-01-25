local socket = require("socket")
math.randomseed(socket.gettime()*1000)
math.random(); math.random(); math.random()

local url = "http://10.96.88.88:5000"

local function randomString(length)
    local str = ""
    for i = 1, length do
        str = str .. string.char(math.random(97, 122)) -- Generates a random lowercase letter
    end
    return str
end

function search(url)
    local accept_ratio = 0.95
    local year_str = tostring(math.random(1, 100000))
    local month = math.random(1, 12)
    local month_str
    if month <= 9 then
        month_str = "0" .. tostring(month)
    else
        month_str = tostring(month)
    end

    -- in_date (in_date_str)
    local coin1 = math.random()
    local coin2 = math.random()
    if coin1 >= accept_ratio or coin2 >= accept_ratio then
        year_str = "2015"
    end
    local in_date_str
    if coin1 < accept_ratio then
        local in_date = math.random(9, 23)

        in_date_str = tostring(in_date)
        if in_date <= 9 then
            in_date_str = year_str .. "-" .. month_str .. "-0" .. in_date_str
        else
            in_date_str = year_str .. "-" .. month_str .. "-" .. in_date_str
        end
    else
        in_date_str = "2015-03-01"
    end

    -- out_date (out_dat_str)
    local out_date_str
    if coin2 < accept_ratio then
        local out_date = math.random(9, 23)

        out_date_str = tostring(out_date)
        if out_date <= 9 then
            out_date_str = year_str .. "-" .. month_str .. "-0" .. out_date_str
        else
            out_date_str = year_str .. "-" .. month_str .. "-" .. out_date_str
        end
    else
        out_date_str = "2015-04-01"
    end

    -- lat (lat, lon)
    local lat
    local lon
    if math.random() < accept_ratio then
        lat = math.random(500000, 1500000)  / 10000.0
        lon = math.random(500000, 1500000)  / 10000.0
    else
        lat = 123
        lon = math.random(500000, 1500000)  / 10000.0
    end

    -- locale (locale_str)
    local locale_str
    if math.random() < accept_ratio then
        locale_str = randomString(20)
    else
        locale_str = "AA"
    end

    -- customer_name (customer_name_str)
    local customer_name_str
    if math.random() < accept_ratio then
        customer_name_str = randomString(20)
    else
        customer_name_str = "Jack"
    end

    local method = "GET"
    local path = url .. "/hotels?inDate=" .. in_date_str ..
      "&outDate=" .. out_date_str .. "&lat=" .. tostring(lat) .. "&lon=" .. tostring(lon) .. "&customerName=" .. customer_name_str .. "&locale=" .. locale_str
    local headers = {}
    -- headers["Content-Type"] = "application/x-www-form-urlencoded"
    return wrk.format(method, path, headers, nil)
end

function dummy(url)
    local method = "GET"
    local path = url .. "/hotels?inDate=2015-04-10&outDate=2015-04-11&lat=38.0235&lon=-122.095"

    local headers = {}
    return wrk.format(method, path, headers, nil)
end

request = function()
    return search(url)
    -- return dummy(url)
end
