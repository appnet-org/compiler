local socket = require("socket")
math.randomseed(socket.gettime()*1000)
math.random(); math.random(); math.random()

local url = "http://localhost:5000"

function search(url)
    local accept_ratio = 0.95
    -- in_date (in_date_str)
    local in_date_str
    if math.random() < accept_ratio then
        local in_date = math.random(9, 23)

        local in_date_str_tmp = tostring(in_date)
        if in_date <= 9 then
            in_date_str = "2015-03-0" .. in_date_str_tmp
        else
            in_date_str = "2015-03-" .. in_date_str_tmp
        end
    else
        in_date_str = "2015-03-01"
    end

    -- out_date (out_dat_str)
    local out_date_str
    if math.random() < accept_ratio then
        local out_date = math.random(9, 23)

        out_date_str = tostring(out_date)
        if out_date <= 9 then
            out_date_str = "2015-04-0" .. out_date_str
        else
            out_date_str = "2015-04-" .. out_date_str
        end
        -- print("Generated date: " .. out_date_str)
    else
        out_date_str = "2015-04-01"
    end

    -- lat (lat, lon)
    local lat
    local lon
    if math.random() < accept_ratio then
        lat = 38.0235 + (math.random(0, 481) - 240.5)/1000.0
        lon = -122.095 + (math.random(0, 325) - 157.0)/1000.0
    else
        lat = 123
        lon = -122.095 + (math.random(0, 325) - 157.0)/1000.0
    end

    -- locale (locale_str)
    local locale_str
    if math.random() < accept_ratio then
        locale_str = "EN"
    else
        locale_str = "AA"
    end

    -- customer_name (customer_name_str)
    local customer_name_str
    if math.random() < accept_ratio then
        customer_name_str = "Andy"
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

request = function()
    return search(url)
end
