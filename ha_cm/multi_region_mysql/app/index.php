<?php
#define connection parameters 
$host = getenv('MYSQL_HOST');
$username = getenv('MYSQL_USERNAME');
$password = getenv('MYSQL_PASSWORD');
$db_name = getenv('DATABASE_NAME');
$pod_name = getenv('POD_NAME');
$node_name= getenv('NODE_NAME');

//Establishes the connection
$conn = mysqli_init();
mysqli_real_connect($conn, $host, $username, $password, $db_name, 3306);
if (mysqli_connect_errno($conn)) {
die('Failed to connect to MySQL: '.mysqli_connect_error());
}



//Run the Select query
$res = mysqli_query($conn, 'SELECT name FROM messages');

if ($res->num_rows > 0) {
    // output data of each row
    while($row = $res->fetch_assoc()) {
        echo "Message: " . $row["name"]. "<br><br><br>";
    }
} else {
    echo "0 results";
}

##print pod and node hostnames 
echo "Data Was Read From Pod: " . gethostname()."<br><br>"; 

echo "Pod is located on Node: " . $node_name."<br><br>";

//Close the connection
mysqli_close($conn);
?>